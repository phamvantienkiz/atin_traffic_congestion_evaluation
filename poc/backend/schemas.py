"""Pydantic request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Point(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class CameraIn(BaseModel):
    name: str = ""
    rtsp_url: str = Field(min_length=1)
    enabled: bool = True
    has_traffic_light: bool = False


class Camera(CameraIn):
    id: str
    zone: list[Point] = Field(default_factory=list)


class ZoneIn(BaseModel):
    points: list[Point]

    @field_validator("points")
    @classmethod
    def check_points(cls, v: list[Point]) -> list[Point]:
        if len(v) not in (0,) and len(v) < 3:
            raise ValueError("Zone phải có ít nhất 3 điểm hoặc rỗng để xóa")
        return v
