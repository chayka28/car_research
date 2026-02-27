from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ADMIN_PASSWORD, ADMIN_USERNAME
from app.core.security import hash_password
from app.db.session import engine
from app.models.car import Car
from app.models.user import User


def seed_data(db: Session) -> None:
    user = db.scalar(select(User).where(User.username == ADMIN_USERNAME))
    if user is None:
        db.add(User(username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD)))

    has_cars = db.scalar(select(Car.id).limit(1))
    if has_cars is None:
        db.add_all(
            [
                Car(
                    brand="BMW",
                    model="X5",
                    year=2020,
                    price=3800000,
                    color="red",
                    link="https://example.com/bmw-x5-1",
                ),
                Car(
                    brand="Toyota",
                    model="Camry",
                    year=2019,
                    price=2200000,
                    color="white",
                    link="https://example.com/toyota-camry-1",
                ),
            ]
        )
    db.commit()


def init_db() -> None:
    with Session(engine) as db:
        seed_data(db)
