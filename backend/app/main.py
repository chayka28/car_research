from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.cars import router as cars_router

app = FastAPI(title="Car Research API")

app.include_router(auth_router)
app.include_router(cars_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
