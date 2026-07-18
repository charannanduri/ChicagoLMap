"""
Looping collector for GitHub Actions.

GitHub cron schedules are best-effort and heavily throttled — a `*/5` cron
in practice fires roughly hourly. So instead the workflow schedules this
module hourly, and it polls the CTA API in a loop every POLL_INTERVAL_SECONDS
for LOOP_MINUTES, giving a true 5-minute collection cadence.

Run as:
    python -m backend.collector.collect_loop
"""
from __future__ import annotations

import logging
import os
import time

from backend.collector.collect_once import main as collect_once

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

LOOP_MINUTES = int(os.getenv("LOOP_MINUTES", "50"))
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))


def main() -> None:
    deadline = time.monotonic() + LOOP_MINUTES * 60
    cycles = 0
    failures = 0

    while True:
        cycles += 1
        try:
            collect_once()
        except Exception:
            failures += 1
            logger.exception("Collection cycle %d failed — continuing", cycles)

        remaining = deadline - time.monotonic()
        if remaining <= POLL_INTERVAL_SECONDS:
            break
        logger.info(
            "Cycle %d done — sleeping %ds (%.1f min left in window)",
            cycles, POLL_INTERVAL_SECONDS, remaining / 60,
        )
        time.sleep(POLL_INTERVAL_SECONDS)

    logger.info("Loop finished: %d cycles, %d failures", cycles, failures)
    if failures and failures == cycles:
        raise SystemExit("every collection cycle failed")


if __name__ == "__main__":
    main()
