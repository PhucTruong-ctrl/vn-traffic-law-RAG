"""Supabase register/login/me endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.auth.service import current_user, login, register
from app.database.session import SupabaseClient, get_db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


class AuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Bearer token required")
    return current_user(client, credentials.credentials)


@router.post("/register")
def register_user(payload: AuthRequest, client: SupabaseClient = Depends(get_db)):  # noqa: B008
    return register(client, payload.email, payload.password)


@router.post("/login")
def login_user(payload: AuthRequest, client: SupabaseClient = Depends(get_db)):  # noqa: B008
    return login(client, payload.email, payload.password)


@router.get("/me")
def me(user: dict = Depends(get_current_user)):  # noqa: B008
    return user
