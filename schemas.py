"""
Database Schemas for the Stream Overlay SaaS

Each Pydantic model represents a collection in MongoDB. The collection
name is the lowercase of the class name (e.g., User -> "user").
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Dict, Any
from datetime import datetime

Locale = Literal["en", "es"]
PlanName = Literal["free", "pro"]
WidgetType = Literal[
    "text",
    "timer",
    "countdown",
    "goal",
    "image",
    "youtube",
    "twitch_alert",
    "minigame_trivia",
    "minigame_poll",
    "leaderboard",
]


class User(BaseModel):
    email: str
    password_hash: Optional[str] = None
    twitch_user_id: Optional[str] = None
    role: Literal["owner", "editor"] = "owner"
    locale: Locale = "en"
    plan: PlanName = "free"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    auth_token: Optional[str] = None  # simple token for session auth


class Overlay(BaseModel):
    owner_user_id: str
    name: str
    width: int = 1920
    height: int = 1080
    secret_token: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Widget(BaseModel):
    overlay_id: str
    type: WidgetType
    x: int = 0
    y: int = 0
    width: int = 300
    height: int = 100
    z_index: int = 0
    logic_config: Dict[str, Any] = Field(default_factory=dict)
    cosmetic_skin_id: Optional[str] = None
    cosmetic_overrides: Dict[str, Any] = Field(default_factory=dict)


class CosmeticSkin(BaseModel):
    name: str
    widget_type: WidgetType
    preview_url: Optional[str] = None
    editable_fields: List[str] = Field(default_factory=list)
    defaults: Dict[str, Any] = Field(default_factory=dict)
    assets: Dict[str, str] = Field(default_factory=dict)
    availability: Literal["free", "subscription", "paid_one_time"] = "free"
    price: Optional[float] = None
    active: bool = True


class UserCosmeticOwnership(BaseModel):
    user_id: str
    skin_id: str
    acquisition_type: Literal["subscription", "purchased", "granted"] = "granted"
    created_at: Optional[datetime] = None


class OverlayPermission(BaseModel):
    overlay_id: str
    user_id: str
    role: Literal["owner", "editor"] = "editor"
    created_at: Optional[datetime] = None


class MinigameConfig(BaseModel):
    widget_id: str
    game_type: Literal["trivia", "poll"]
    mode: Literal["manual", "loop"] = "manual"
    loop_interval_seconds: Optional[int] = None
    is_loop_enabled: bool = False
    settings: Dict[str, Any] = Field(default_factory=dict)


class Points(BaseModel):
    overlay_id: str
    twitch_username: str
    points: int = 0
    updated_at: Optional[datetime] = None


class Plan(BaseModel):
    name: PlanName
    description: str


class FeatureFlag(BaseModel):
    feature_key: str
    plan_name: PlanName
    allowed: bool = True
