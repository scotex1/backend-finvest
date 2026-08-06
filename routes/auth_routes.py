"""
routes/auth_routes.py — /api/v1/auth/*
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, EmailStr
from services.auth_service import AuthService

router = APIRouter()


class SyncUserRequest(BaseModel):
    uid:   str
    email: EmailStr
    name:  str = ""
    photo: str = ""


class UpdateProfileRequest(BaseModel):
    name:       str | None = None
    phone:      str | None = None
    city:       str | None = None
    occupation: str | None = None
    income:     str | None = None


# POST /api/v1/auth/sync
@router.post("/sync")
async def sync_user(body: SyncUserRequest, request: Request):
    """Called from frontend on every login to sync user with Firestore."""
    # Allow even without middleware token (called during auth flow)
    try:
        result = AuthService.sync_user(
            uid=body.uid,
            email=body.email,
            name=body.name,
            photo=body.photo,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
