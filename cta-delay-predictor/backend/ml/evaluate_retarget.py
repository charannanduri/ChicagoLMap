"""
Decide whether the retargeted model is worth shipping.

The product claims to correct the CTA's arrival estimate. The honest benchmark
for that claim is "trust the CTA exactly" — i.e. predict an error of zero. If a
model cannot beat that, there is no correction to sell, and we should say so
rather than ship a pill that quietly agrees with the number beside it.

This trains on the new target (cta_error_minutes) and reports skill against
that benchmark. It writes no model artifacts and changes nothing in serving —
it exists to produce a number we can act on.

Run as:
    python -m backend.ml.evaluate_retarget
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import sqlalchemy
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from backend.db.session import SessionLocal
from backend.ml.features import ALL_FEATURES, BOOL_FEATURES, NUMERIC_FEATURES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TARGET = "cta_error_minutes"
MIN_ROWS = 500

# Features the offline table has but the live serving path does not currently
# populate — stations.py/predict.py send 0 for all four. Training with them and
# serving without them is train/serve skew, so any skill they carry is skill we
# do not actually get in production. The "serve-time only" arm below drops them
# from both train and test, which is the number that honestly describes today's
# deployment. The gap between the two arms is the prize for wiring them up.
SKEWED_FEATURES = [
    "eta_delta_1_min",
    "eta_delta_2_min",
    "headway_before_min",
    "headway_after_min",
]
# Errors beyond this are almost always a mis-joined arrival rather than a real
# CTA miss; keeping them would let a handful of rows dominate the loss.
CLIP_MIN = 20.0


def _load() -> pd.DataFrame:
    cols = list(dict.fromkeys(ALL_FEATURES + [TARGET, "snapshot_time", "route", "station_id"]))
    with SessionLocal() as db:
        result = db.execute(sqlalchemy.text(
            f"SELECT {', '.join(cols)} FROM model_features "
            f"WHERE {TARGET} IS NOT NULL ORDER BY snapshot_time"
        ))
        rows = result.fetchall()
        names = list(result.keys())
    if not rows:
        raise RuntimeError(
            f"No rows with {TARGET}. Run backend.etl.backfill_cta_error first."
        )
    return pd.DataFrame(rows, columns=names)


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    for c in BOOL_FEATURES:
        if c in df.columns:
            df[c] = df[c].fillna(False).astype(int)
    for c in NUMERIC_FEATURES:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce")
    df = df.dropna(subset=[TARGET])
    return df[df[TARGET].abs() <= CLIP_MIN].copy()


def main() -> None:
    df = _prep(_load())
    logger.info("Loaded %d usable rows", len(df))
    if len(df) < MIN_ROWS:
        raise SystemExit(f"Only {len(df)} rows — need {MIN_ROWS}. Collect more data.")

    df = df.sort_values("snapshot_time").reset_index(drop=True)
    split = max(1, int(len(df) * 0.8))
    train_df, test_df = df.iloc[:split], df.iloc[split:]

    X_tr = train_df[ALL_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(0)
    X_te = test_df[ALL_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(0)
    y_tr, y_te = train_df[TARGET].values, test_df[TARGET].values

    # The benchmark: assume the CTA is exactly right.
    mae_trust_cta = mean_absolute_error(y_te, np.zeros_like(y_te))
    # A second reference: the best constant, i.e. a systematic bias correction.
    mae_constant = mean_absolute_error(y_te, np.full_like(y_te, np.median(y_tr)))

    ridge = Pipeline([("s", StandardScaler()), ("m", Ridge(alpha=1.0))]).fit(X_tr, y_tr)
    mae_ridge = mean_absolute_error(y_te, ridge.predict(X_te))

    def _fit_xgb(cols: list[str]) -> tuple[XGBRegressor, np.ndarray, float]:
        m = XGBRegressor(
            n_estimators=400, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=4,
        ).fit(X_tr[cols], y_tr)
        p = m.predict(X_te[cols])
        return m, p, mean_absolute_error(y_te, p)

    xgb, _, mae_xgb = _fit_xgb(ALL_FEATURES)

    # What the deployed service can actually do today.
    serve_cols = [c for c in ALL_FEATURES if c not in SKEWED_FEATURES]
    xgb_serve, pred, mae_serve = _fit_xgb(serve_cols)
    xgb_serve_importance = xgb_serve.feature_importances_

    skill = (1 - mae_serve / mae_trust_cta) * 100 if mae_trust_cta else 0.0
    skill_full = (1 - mae_xgb / mae_trust_cta) * 100 if mae_trust_cta else 0.0

    # Product-relevant: how often would the corrected minute differ from the
    # CTA's? This is the number that decides whether the pill earns its place.
    eta = X_te["minutes_until_arrival"].values
    shown_cta = np.maximum(0, np.rint(eta))
    shown_ours = np.maximum(0, np.rint(eta + pred))
    differs = (shown_cta != shown_ours).mean() * 100

    print("=" * 64)
    print("RETARGET EVALUATION — target: actual arrival minus CTA prediction")
    print("=" * 64)
    print(f"  rows                    {len(df):,}   (train {len(train_df):,} / test {len(test_df):,})")
    print(f"  span                    {df.snapshot_time.min()}  ->  {df.snapshot_time.max()}")
    print()
    print("  TARGET DISTRIBUTION (test)")
    print(f"    mean                  {y_te.mean():+.3f} min")
    print(f"    std                   {y_te.std():.3f} min")
    print(f"    p10 / p50 / p90       {np.percentile(y_te,10):+.2f} / "
          f"{np.percentile(y_te,50):+.2f} / {np.percentile(y_te,90):+.2f} min")
    print(f"    |error| >= 1 min      {(np.abs(y_te)>=1).mean()*100:.1f}% of arrivals")
    print(f"    |error| >= 2 min      {(np.abs(y_te)>=2).mean()*100:.1f}% of arrivals")
    print()
    print("  MEAN ABSOLUTE ERROR")
    print(f"    trust the CTA (0)     {mae_trust_cta:.3f} min   <- benchmark to beat")
    print(f"    best constant         {mae_constant:.3f} min")
    print(f"    ridge                 {mae_ridge:.3f} min")
    print(f"    xgboost, all features {mae_xgb:.3f} min   (needs serving work)")
    print(f"    xgboost, serve-time   {mae_serve:.3f} min   <- what ships today")
    print()
    print(f"  SKILL vs trusting CTA   {skill:+.1f}%   (serve-time features only)")
    print(f"    if we also wire up {', '.join(SKEWED_FEATURES)}:")
    print(f"                          {skill_full:+.1f}%")
    print(f"  would change the shown minute for {differs:.1f}% of arrivals")
    print()
    imp = sorted(zip(serve_cols, xgb_serve_importance), key=lambda t: -t[1])[:8]
    print("  TOP FEATURES (serve-time model)")
    for name, val in imp:
        print(f"    {name:<26} {val*100:5.1f}%")
    print()
    if skill <= 1:
        print("  VERDICT: no meaningful correction. The CTA's own estimate is as")
        print("  good as anything we can predict from these features. Drop the")
        print("  prediction claim and lead with the map and trip tracking.")
    elif skill < 8:
        print("  VERDICT: marginal. Real but small. Worth showing only as a range,")
        print("  never as a confident point estimate.")
    else:
        print("  VERDICT: genuine skill. Ship it — show one corrected number with")
        print("  its confidence range, and retire the duelling pills.")
    print("=" * 64)


if __name__ == "__main__":
    main()
