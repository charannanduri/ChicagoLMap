"""
Offline model training script.

Predicts how wrong the CTA's own live arrival estimate will turn out to be,
in minutes. The honest benchmark is therefore "trust the CTA exactly" -- i.e.
predict zero -- and the models below are only worth shipping if they beat it.
On the most recent evaluation the XGBoost regressor reached 1.333 min MAE
against that benchmark's 1.663, roughly 20% skill, using only features the
serving path can actually supply. See backend/ml/evaluate_retarget.py.

Loads labeled rows from model_features, splits by time, trains:
  1. BaselineMedian  — historical median error by route × station × hour × weekday/weekend
  2. Ridge regression
  3. XGBoost regressor (primary)
  4. XGBoost classifier (ahead / on_time / behind, relative to the CTA estimate)

Saves artifacts to settings.model_dir with joblib.

Run:
    python -m backend.ml.train
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import joblib
import matplotlib
matplotlib.use("Agg")  # headless — no display needed in CI
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    root_mean_squared_error,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier, XGBRegressor

from backend.config import get_settings
from backend.db.session import SessionLocal
from backend.ml.features import (
    ALL_FEATURES,
    BOOL_FEATURES,
    NUMERIC_FEATURES,
    SERVING_FEATURES,
    STATUS_LABELS,
    TARGET_CLIP_MIN,
    TARGET_REGRESSION,
    derive_status,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

settings = get_settings()


def _load_data() -> pd.DataFrame:
    # Selects ALL_FEATURES even though the model fits SERVING_FEATURES: the
    # extra columns cost nothing to load and keep the retired ones available
    # for comparison. dict.fromkeys deduplicates while preserving order.
    select_cols = list(dict.fromkeys(
        ALL_FEATURES + [TARGET_REGRESSION, "snapshot_time", "route", "station_id"]
    ))
    import sqlalchemy
    with SessionLocal() as db:
        result = db.execute(
            sqlalchemy.text(
                f"SELECT {', '.join(select_cols)} FROM model_features "
                f"WHERE {TARGET_REGRESSION} IS NOT NULL ORDER BY snapshot_time"
            )
        )
        rows = result.fetchall()
        col_names = list(result.keys())  # capture before session closes
    if not rows:
        raise RuntimeError("No labeled rows in model_features. Collect data first.")
    df = pd.DataFrame(rows, columns=col_names)
    return df


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    for col in BOOL_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(int)
    for col in NUMERIC_FEATURES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df[TARGET_REGRESSION] = pd.to_numeric(df[TARGET_REGRESSION], errors="coerce")
    df = df.dropna(subset=[TARGET_REGRESSION])

    # Drop implausible errors before they dominate the loss, then derive the
    # three-class label from the same number the regressor is fit on, so the
    # two heads can never disagree about what the row represents.
    before = len(df)
    df = df[df[TARGET_REGRESSION].abs() <= TARGET_CLIP_MIN].copy()
    if before != len(df):
        logger.info(
            "Dropped %d row(s) with |%s| > %.0f min as likely mis-joins",
            before - len(df), TARGET_REGRESSION, TARGET_CLIP_MIN,
        )
    df["delay_status"] = df[TARGET_REGRESSION].map(derive_status)
    return df


def _time_split(df: pd.DataFrame, test_frac: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Temporal train/test split by row fraction.

    Sorts by time and uses the last `test_frac` of rows as the test set.
    More robust than a fixed day window when data history is short (e.g.
    the first week of collection) — always guarantees non-empty train/test.
    """
    df = df.sort_values("snapshot_time").reset_index(drop=True)
    split = max(1, int(len(df) * (1 - test_frac)))
    return df.iloc[:split].copy(), df.iloc[split:].copy()


class BaselineMedianModel:
    """Historical median delay by route × station × hour × is_weekend."""

    def __init__(self) -> None:
        self._medians: dict[tuple, float] = {}
        self._global_median: float = 0.0

    def fit(self, df: pd.DataFrame) -> "BaselineMedianModel":
        self._global_median = float(df[TARGET_REGRESSION].median())
        grp = df.groupby(["route", "station_id", "hour_of_day", "is_weekend"])[TARGET_REGRESSION].median()
        self._medians = grp.to_dict()
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        def _lookup(row: pd.Series) -> float:
            key = (row["route"], row["station_id"], row["hour_of_day"], int(row["is_weekend"]))
            return self._medians.get(key, self._global_median)

        return np.array(df.apply(_lookup, axis=1))


MIN_ROWS = 500


# ── evaluation helpers ────────────────────────────────────────────────────────

def _write_step_summary(metrics: dict[str, dict]) -> None:
    """Write a markdown metrics table to $GITHUB_STEP_SUMMARY (CI only)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        "## CTA Delay Predictor — Training Results\n",
        "| Model | MAE (min) | RMSE (min) |",
        "|---|---|---|",
    ]
    for name, m in metrics.items():
        if "mae" not in m:
            continue  # skip classifier entry (has acc/f1, not mae/rmse)
        lines.append(f"| {name} | {m['mae']:.3f} | {m['rmse']:.3f} |")
    lines += [
        "",
        "### Classifier (XGBoost)",
        f"- Accuracy: **{metrics.get('xgb_classifier', {}).get('acc', 0):.3f}**",
        f"- Macro F1:  **{metrics.get('xgb_classifier', {}).get('f1', 0):.3f}**",
        "",
        "> Plots saved to `ml_models/plots/` in the artifact.",
    ]
    with open(path, "a") as f:
        f.write("\n".join(lines) + "\n")


def _save_plots(
    model_dir: Path,
    xgb_reg: XGBRegressor,
    y_test: pd.Series,
    y_pred_reg: np.ndarray,
    y_test_cls: pd.Series,
    y_pred_cls: np.ndarray,
    label_map: dict[str, int],
) -> None:
    """Generate and save 4 evaluation plots to model_dir/plots/."""
    plot_dir = model_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    inv_label = {v: k for k, v in label_map.items()}
    class_names = [inv_label.get(i, str(i)) for i in sorted(inv_label)]

    sns.set_theme(style="darkgrid", palette="muted")

    # ── 1. Feature importance ─────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 6))
    # Indexed by what the model was actually fit on. Using ALL_FEATURES here
    # would pair 20 labels with 15 importances and raise.
    importances = pd.Series(xgb_reg.feature_importances_, index=SERVING_FEATURES)
    importances.sort_values().tail(15).plot.barh(ax=ax, color="#4A9EFF")
    ax.set_title("XGBoost Feature Importance (top 15)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Importance score")
    fig.tight_layout()
    fig.savefig(plot_dir / "feature_importance.png", dpi=120)
    plt.close(fig)

    # ── 2. Actual vs predicted (scatter + diagonal) ───────────────────────────
    fig, ax = plt.subplots(figsize=(7, 7))
    lo = min(y_test.min(), y_pred_reg.min()) - 1
    hi = max(y_test.max(), y_pred_reg.max()) + 1
    ax.scatter(y_test, y_pred_reg, alpha=0.35, s=18, color="#4A9EFF", label="Predictions")
    ax.plot([lo, hi], [lo, hi], "r--", linewidth=1.5, label="Perfect fit")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Actual delay (min)")
    ax.set_ylabel("Predicted delay (min)")
    ax.set_title("Actual vs Predicted Delay", fontsize=13, fontweight="bold")
    ax.legend()
    fig.tight_layout()
    fig.savefig(plot_dir / "actual_vs_predicted.png", dpi=120)
    plt.close(fig)

    # ── 3. Residuals distribution ─────────────────────────────────────────────
    residuals = y_pred_reg - y_test.values
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(residuals, bins=40, color="#4A9EFF", edgecolor="white", linewidth=0.4)
    ax.axvline(0, color="red", linestyle="--", linewidth=1.5)
    ax.set_xlabel("Residual (predicted − actual, minutes)")
    ax.set_ylabel("Count")
    ax.set_title("Prediction Residuals", fontsize=13, fontweight="bold")
    ax.text(
        0.97, 0.95, f"Mean: {residuals.mean():.2f} min\nStd: {residuals.std():.2f} min",
        transform=ax.transAxes, ha="right", va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.7),
    )
    fig.tight_layout()
    fig.savefig(plot_dir / "residuals.png", dpi=120)
    plt.close(fig)

    # ── 4. Confusion matrix (counts + row-% so per-class recall is clear) ────
    cm = confusion_matrix(y_test_cls, y_pred_cls, labels=sorted(inv_label))
    cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True).clip(min=1)
    annot = np.array(
        [[f"{cm[i,j]}\n({cm_norm[i,j]:.0%})" for j in range(cm.shape[1])]
         for i in range(cm.shape[0])]
    )
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(
        cm_norm, annot=annot, fmt="", cmap="Blues",
        xticklabels=class_names, yticklabels=class_names, ax=ax,
        vmin=0, vmax=1,
    )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Classifier Confusion Matrix\n(count + row %)", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(plot_dir / "confusion_matrix.png", dpi=120)
    plt.close(fig)

    logger.info("Plots saved to %s", plot_dir)


def train() -> None:
    logger.info("Loading labeled features…")
    df_raw = _load_data()
    df = _prep(df_raw)
    logger.info("Loaded %d labeled rows", len(df))

    if len(df) < MIN_ROWS:
        logger.warning(
            "Only %d labeled rows — need at least %d to train. "
            "Run ETL and collect more data first.",
            len(df), MIN_ROWS,
        )
        return

    train_df, test_df = _time_split(df)
    logger.info("Train: %d rows, Test: %d rows", len(train_df), len(test_df))

    # Missing values stay NaN rather than becoming 0. Zero is a claim -- "the
    # ETA did not move", "the trains arrive together" -- and serving genuinely
    # does not know these for every prediction. XGBoost learns a default split
    # direction for NaN, so the two sides now agree on what "unknown" means.
    # See backend/ml/serving_features.py.
    # SERVING_FEATURES, not ALL_FEATURES: fit only on what every caller can
    # supply at request time. Training on the five the map cannot produce cost
    # 0.3 points of skill to drop (19.8% -> 19.5%) and made the map predict
    # about +7 minutes for every train, because XGBoost had no training rows
    # where they were missing and its default NaN direction was untrained.
    X_train = train_df[SERVING_FEATURES].astype(float)
    y_train = train_df[TARGET_REGRESSION]
    X_test = test_df[SERVING_FEATURES].astype(float)
    y_test = test_df[TARGET_REGRESSION]

    # Status labels (map string → int for XGB classifier)
    label_map = {lbl: i for i, lbl in enumerate(STATUS_LABELS)}
    inv_label_map = {v: k for k, v in label_map.items()}
    y_train_cls = train_df["delay_status"].map(label_map).fillna(1)
    y_test_cls = test_df["delay_status"].map(label_map).fillna(1)

    # Inverse-frequency sample weights so the classifier doesn't ignore the
    # minority "ahead" / "behind" classes (on_time typically dominates 70-80%).
    _counts = y_train_cls.value_counts()
    _n, _k = len(y_train_cls), len(_counts)
    _class_weights = {cls: _n / (_k * cnt) for cls, cnt in _counts.items()}
    sample_weight_train = y_train_cls.map(_class_weights)
    logger.info(
        "Classifier class weights: %s",
        {inv_label_map.get(k, k): f"{v:.2f}" for k, v in _class_weights.items()},
    )

    model_dir = Path(settings.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, dict] = {}

    def _reg_metrics(name: str, y_true: pd.Series, y_pred: np.ndarray) -> None:
        mae = mean_absolute_error(y_true, y_pred)
        rmse = root_mean_squared_error(y_true, y_pred)
        logger.info("[%s] MAE=%.3f min  RMSE=%.3f min", name, mae, rmse)
        summary[name] = {"mae": mae, "rmse": rmse}

    def _cls_metrics(name: str, y_true: pd.Series, y_pred: np.ndarray) -> None:
        acc = accuracy_score(y_true, y_pred)
        f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
        logger.info("[%s] Accuracy=%.3f  Macro-F1=%.3f", name, acc, f1)
        summary[name] = {"acc": acc, "f1": f1}

    # 1. Baseline median
    logger.info("Training BaselineMedianModel…")
    baseline = BaselineMedianModel().fit(train_df)
    _reg_metrics("baseline", y_test, baseline.predict(test_df))
    joblib.dump(baseline, model_dir / "baseline.joblib")

    # 2. Ridge regression
    logger.info("Training Ridge regression…")
    # Ridge cannot express "unknown", so it gets median imputation. The
    # XGBoost models below take NaN directly, which is why they are the ones
    # that ship.
    ridge = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("ridge", Ridge(alpha=1.0)),
    ])
    ridge.fit(X_train, y_train)
    _reg_metrics("ridge", y_test, ridge.predict(X_test))
    joblib.dump(ridge, model_dir / "ridge.joblib")

    # 3. XGBoost regressor
    logger.info("Training XGBoost regressor…")
    xgb_reg = XGBRegressor(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    xgb_reg.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    _reg_metrics("xgb_regressor", y_test, xgb_reg.predict(X_test))
    joblib.dump(xgb_reg, model_dir / "xgb_regressor.joblib")

    # XGBoost quantile regressors (p10 / p90)
    for alpha, tag in [(0.1, "p10"), (0.9, "p90")]:
        qreg = XGBRegressor(
            objective="reg:quantileerror",
            quantile_alpha=alpha,
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )
        qreg.fit(X_train, y_train)
        joblib.dump(qreg, model_dir / f"xgb_{tag}.joblib")
    logger.info("Quantile models saved (p10, p90)")

    # 4. XGBoost classifier
    logger.info("Training XGBoost classifier…")
    xgb_cls = XGBClassifier(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    xgb_cls.fit(
        X_train, y_train_cls,
        sample_weight=sample_weight_train,
        eval_set=[(X_test, y_test_cls)],
        verbose=False,
    )
    y_pred_cls = xgb_cls.predict(X_test)
    _cls_metrics("xgb_classifier", y_test_cls, y_pred_cls)
    joblib.dump(xgb_cls, model_dir / "xgb_classifier.joblib")
    joblib.dump(label_map, model_dir / "label_map.joblib")

    logger.info("All models saved to %s", model_dir)

    y_pred_reg = xgb_reg.predict(X_test)
    _save_plots(model_dir, xgb_reg, y_test, y_pred_reg, y_test_cls, y_pred_cls, label_map)
    _write_step_summary(summary)


if __name__ == "__main__":
    train()
