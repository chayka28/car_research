from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_username
from app.db.session import get_db
from app.models.car import Car
from app.schemas.car import CarOut

router = APIRouter(prefix="/api", tags=["cars"])


@router.get("/cars", response_model=List[CarOut])
def list_cars(_: str = Depends(get_current_username), db: Session = Depends(get_db)) -> List[CarOut]:
    cars = db.scalars(select(Car).order_by(Car.id.desc())).all()
    return [
        CarOut(
            brand=car.brand,
            model=car.model,
            year=car.year,
            price=car.price,
            color=car.color,
            link=car.link,
        )
        for car in cars
    ]
