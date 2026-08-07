"""
End-to-end smoke test against the LIVE public services.

Checks the whole user-facing stack the way a real client uses it: the map app's
endpoints, the predictor service, and every endpoint added recently that has not
otherwise been exercised in production.

Exits non-zero if any REQUIRED check fails. Optional checks report but do not
fail the run — they cover behaviour that legitimately varies (there may be no
active service alerts, and free-tier services cold-start slowly).

Usage:
    python -m backend.smoke_test
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

MAP_URL = "https://chicagolmap.onrender.com"
PREDICTOR_URL = "https://cta-delay-api.onrender.com"
TIMEOUT = 45  # generous: free-tier instances cold-start

results: list[tuple[str, bool, bool, str]] = []  # (name, ok, required, detail)


def _send(req: urllib.request.Request) -> tuple[int, object]:
    """Send a request, returning (status, parsed body).

    An error response is returned rather than raised, because its body usually
    carries the reason — losing that turns a diagnosable failure into a bare
    status code.
    """
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        status = exc.code
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


def _get(url: str) -> tuple[int, object]:
    return _send(urllib.request.Request(url, headers={"User-Agent": "chicagolmap-smoke/1.0"}))


def _post(url: str, payload: dict) -> tuple[int, object]:
    return _send(urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "chicagolmap-smoke/1.0"},
    ))


def check(name: str, required: bool = True):
    """Decorator-ish helper: run fn, record pass/fail with a detail string."""
    def run(fn):
        try:
            detail = fn()
            results.append((name, True, required, detail or "ok"))
        except Exception as exc:  # noqa: BLE001 — a failed check is data, not a crash
            results.append((name, False, required, f"{type(exc).__name__}: {exc}"))
        return fn
    return run


def main() -> None:
    print("=" * 72)
    print("LIVE SMOKE TEST")
    print("=" * 72)

    state: dict = {}

    @check("map: /api/trains/red returns live trains")
    def _():
        status, data = _get(f"{MAP_URL}/api/trains/red")
        assert status == 200, f"HTTP {status}"
        trains = data.get("trains", [])
        assert trains, "no trains returned"
        run = next((t.get("run_number") for t in trains if t.get("run_number")), None)
        state["run_number"] = run
        return f"{len(trains)} trains, source={data.get('position_source')}"

    @check("predictor: /health reports model + db ready")
    def _():
        status, data = _get(f"{PREDICTOR_URL}/health")
        assert status == 200, f"HTTP {status}"
        assert data.get("model_ready") is True, f"model_ready={data.get('model_ready')}"
        assert data.get("db_ok") is True, f"db_ok={data.get('db_ok')}"
        return f"model_ready={data['model_ready']} db_ok={data['db_ok']} snapshots={data.get('snapshot_count')}"

    @check("map: station arrivals include ML predictions")
    def _():
        # 40900 = Howard (Red Line terminal), reliably busy.
        status, data = _get(f"{MAP_URL}/api/station/40900/arrivals?n=12")
        assert status == 200, f"HTTP {status}"
        trains = [t for d in data.get("directions", []) for t in d.get("trains", [])]
        assert trains, "no arrivals returned"
        predicted = [t for t in trains if t.get("predictor_active") and t.get("delay_minutes") is not None]
        assert predicted, (
            f"{len(trains)} arrivals but NONE carry an ML prediction "
            "(predictor unreachable from the map app?)"
        )
        return f"{len(predicted)}/{len(trains)} arrivals have predictions"

    @check("map: /api/alerts (service alerts)")
    def _():
        status, data = _get(f"{MAP_URL}/api/alerts")
        assert status == 200, f"HTTP {status}"
        alerts = data.get("alerts")
        assert isinstance(alerts, list), "alerts is not a list"
        return f"{len(alerts)} active alert(s)"

    @check("map: /api/run/<run>/follow (trip tracking)")
    def _():
        run = state.get("run_number")
        assert run, "no run number available from the trains check"
        status, data = _get(f"{MAP_URL}/api/run/{run}/follow")
        assert status == 200, f"HTTP {status}"
        stops = data.get("stops", [])
        assert stops, f"run {run} returned no upcoming stops"
        with_pred = [s for s in stops if s.get("predicted_arrival_time")]
        return f"run {run}: {len(stops)} stops, {len(with_pred)} with predicted times"

    # A no-op correction (delta 0): records a row without skewing any data.
    feedback_payload = {
        "run_number": state.get("run_number") or "0",
        "station_id": "40900",
        "route": "Red",
        "predicted_delay_minutes": 1.0,
        "delta_minutes": 0,
    }

    # Test the predictor directly first — it owns the write. Distinguishes
    # "route not deployed" (404) from "write rejected" (503) from a relay
    # problem in the map app, which a 502 from the map app alone cannot.
    @check("predictor: POST /feedback (direct)")
    def _():
        status, data = _post(f"{PREDICTOR_URL}/feedback", dict(feedback_payload))
        if status == 404:
            raise AssertionError("route missing — predictor service is running an older build")
        assert status == 200, f"HTTP {status}: {data}"
        assert data.get("ok") is True, f"response={data}"
        return f"recorded id={data.get('id')}"

    @check("map: POST /api/feedback (relayed)")
    def _():
        status, data = _post(f"{MAP_URL}/api/feedback", dict(feedback_payload))
        assert status == 200, f"HTTP {status}: {data}"
        assert data.get("ok") is True, f"response={data}"
        return f"recorded id={data.get('id')}"

    # ---- report -----------------------------------------------------------
    print()
    failed_required = 0
    for name, ok, required, detail in results:
        mark = "PASS" if ok else ("FAIL" if required else "WARN")
        if not ok and required:
            failed_required += 1
        print(f"  [{mark}] {name}")
        print(f"         {detail}")

    print()
    print("=" * 72)
    total = len(results)
    passed = sum(1 for _, ok, _, _ in results if ok)
    print(f"{passed}/{total} checks passed")
    if failed_required:
        print(f"{failed_required} REQUIRED check(s) failed")
        sys.exit(1)
    print("All required checks passed.")


if __name__ == "__main__":
    main()
