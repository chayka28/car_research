from fastapi import APIRouter, HTTPException, status

from app.core.security import create_access_token, verify_password
from app.db.fake_data import ADMIN_USER
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    if payload.username != ADMIN_USER["username"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(payload.password, ADMIN_USER["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(subject=payload.username)
    return TokenResponse(access_token=token)
