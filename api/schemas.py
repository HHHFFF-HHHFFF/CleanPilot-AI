"""HTTP 接口的请求与响应数据契约。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUserResponse(BaseModel):
    user_id: str
    display_name: str
    city: str
    role: str
    device: dict[str, str] | None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4000)
    location_profile: dict[str, Any] | None = None


class CoordinatesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CityWeatherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str = Field(min_length=1, max_length=100)
