"""Pydantic schemas for auth requests and responses."""

from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime


class RegisterRequest(BaseModel):
    email: EmailStr = Field(..., example="test@test.com")
    password: str = Field(..., min_length=8, example="password")


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., example="test@test.com")
    password: str = Field(..., example="password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    user_id: UUID
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
