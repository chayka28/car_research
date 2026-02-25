import logging
import time

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.client import fetch_payload_with_retry, normalize_cars
from app.config import SCRAPER_INTERVAL_SECONDS, WORKER_RUN_ONCE
from app.db import SessionLocal
from app.models import Car


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def upsert_cars(cars: list[dict[str, object]]) -> None:
    if not cars:
        logger.info("No valid cars to upsert.")
        return

    with SessionLocal() as session:
        stmt = pg_insert(Car).values(cars)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Car.link],
            set_={
                "brand": stmt.excluded.brand,
                "model": stmt.excluded.model,
                "year": stmt.excluded.year,
                "price": stmt.excluded.price,
                "color": stmt.excluded.color,
            },
        )
        session.execute(stmt)
        session.commit()

    logger.info("Upserted %s cars.", len(cars))


def run_cycle() -> None:
    payload = fetch_payload_with_retry()
    cars = normalize_cars(payload)
    upsert_cars(cars)


def main() -> None:
    logger.info("Carsensor worker started. run_once=%s, interval=%ss", WORKER_RUN_ONCE, SCRAPER_INTERVAL_SECONDS)

    while True:
        started = time.time()
        try:
            run_cycle()
        except Exception:
            logger.exception("Worker cycle failed.")

        if WORKER_RUN_ONCE:
            logger.info("Run-once mode enabled. Worker stopping.")
            return

        elapsed = time.time() - started
        sleep_seconds = max(1, SCRAPER_INTERVAL_SECONDS - int(elapsed))
        logger.info("Next cycle in %ss.", sleep_seconds)
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
