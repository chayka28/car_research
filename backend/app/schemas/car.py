from pydantic import BaseModel


class CarOut(BaseModel):
    brand: str
    model: str
    year: int
    price: int
    color: str
    link: str
