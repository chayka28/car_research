from typing import List

from fastapi import APIRouter, Depends

from app.api.deps import get_current_username
from app.db.fake_data import CARS
from app.schemas.car import CarOut

router = APIRouter(prefix="/api", tags=["cars"])


@router.get("/cars", response_model=List[CarOut])
def list_cars(_: str = Depends(get_current_username)) -> List[CarOut]:
    return [CarOut(**car) for car in CARS]
