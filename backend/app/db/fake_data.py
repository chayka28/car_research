from app.core.config import ADMIN_PASSWORD, ADMIN_USERNAME
from app.core.security import hash_password

ADMIN_USER = {
    "username": ADMIN_USERNAME,
    "password_hash": hash_password(ADMIN_PASSWORD),
}

CARS = [
    {
        "brand": "BMW",
        "model": "X5",
        "year": 2020,
        "price": 3800000,
        "color": "red",
        "link": "https://example.com/bmw-x5-1",
    },
    {
        "brand": "Toyota",
        "model": "Camry",
        "year": 2019,
        "price": 2200000,
        "color": "white",
        "link": "https://example.com/toyota-camry-1",
    },
]
