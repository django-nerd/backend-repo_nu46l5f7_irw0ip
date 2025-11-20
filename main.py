import os
import secrets
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Header
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import (
    User, Overlay, Widget, CosmeticSkin, UserCosmeticOwnership, OverlayPermission,
    MinigameConfig, Points, Plan, FeatureFlag
)

app = FastAPI(title="Stream Overlay SaaS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str


class CreateOverlayRequest(BaseModel):
    name: str
    width: int = 1920
    height: int = 1080


class CreateWidgetRequest(BaseModel):
    overlay_id: str
    type: str
    x: int = 0
    y: int = 0
    width: int = 300
    height: int = 100
    z_index: int = 0
    logic_config: Dict[str, Any] = {}
    cosmetic_skin_id: Optional[str] = None
    cosmetic_overrides: Dict[str, Any] = {}


class UpdateWidgetRequest(BaseModel):
    widget_id: str
    updates: Dict[str, Any]


# Simple auth dependency using a bearer-like token
async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.replace("Bearer ", "")
    user = db["user"].find_one({"auth_token": token})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@app.get("/")
def root():
    return {"message": "Stream Overlay SaaS API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"

    return response


# Auth endpoints (email+password minimal MVP)
@app.post("/auth/signup", response_model=AuthResponse)
def signup(payload: AuthRequest):
    existing = db["user"].find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    token = secrets.token_hex(16)
    user = User(email=payload.email, password_hash=payload.password, auth_token=token)
    user_id = create_document("user", user)
    return {"token": token, "user_id": user_id}


@app.post("/auth/signin", response_model=AuthResponse)
def signin(payload: AuthRequest):
    user = db["user"].find_one({"email": payload.email, "password_hash": payload.password})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = user.get("auth_token") or secrets.token_hex(16)
    if not user.get("auth_token"):
        db["user"].update_one({"_id": user["_id"]}, {"$set": {"auth_token": token}})
    return {"token": token, "user_id": str(user["_id"]) }


# Plan/feature gating simple defaults
DEFAULT_FEATURES = [
    FeatureFlag(feature_key="widget.text", plan_name="free", allowed=True),
    FeatureFlag(feature_key="widget.timer", plan_name="free", allowed=True),
    FeatureFlag(feature_key="widget.countdown", plan_name="free", allowed=True),
    FeatureFlag(feature_key="widget.youtube", plan_name="pro", allowed=True),
    FeatureFlag(feature_key="widget.goal", plan_name="pro", allowed=True),
    FeatureFlag(feature_key="widget.twitch_alert", plan_name="pro", allowed=True),
    FeatureFlag(feature_key="widget.minigame_trivia", plan_name="pro", allowed=True),
    FeatureFlag(feature_key="widget.minigame_poll", plan_name="pro", allowed=True),
    FeatureFlag(feature_key="widget.leaderboard", plan_name="pro", allowed=True),
]


def can_use_widget_type(user: dict, widget_type: str) -> bool:
    plan = user.get("plan", "free")
    feature_key = f"widget.{widget_type}"
    # Check DB overrides first
    flag = db["featureflag"].find_one({"feature_key": feature_key, "plan_name": plan})
    if flag:
        return bool(flag.get("allowed", False))
    # Fallback to defaults
    for f in DEFAULT_FEATURES:
        if f.feature_key == feature_key and f.plan_name == plan:
            return f.allowed
    return False


# Overlays
@app.get("/overlays", response_model=List[Dict[str, Any]])
def list_overlays(user=Depends(get_current_user)):
    docs = list(db["overlay"].find({"owner_user_id": str(user["_id"])}))
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@app.post("/overlays", response_model=Dict[str, Any])
def create_overlay(payload: CreateOverlayRequest, user=Depends(get_current_user)):
    secret = secrets.token_urlsafe(16)
    overlay = Overlay(
        owner_user_id=str(user["_id"]),
        name=payload.name,
        width=payload.width,
        height=payload.height,
        secret_token=secret,
    )
    overlay_id = create_document("overlay", overlay)
    return {"id": overlay_id, "secret_token": secret}


@app.delete("/overlays/{overlay_id}")
def delete_overlay(overlay_id: str, user=Depends(get_current_user)):
    doc = db["overlay"].find_one({"_id": {"$eq": db["overlay"].codec_options.document_class.objectid_class(overlay_id)}})
    # Fallback simple check using string compare
    if not doc:
        doc = db["overlay"].find_one({"_id": overlay_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Overlay not found")
    if doc.get("owner_user_id") != str(user["_id"]):
        raise HTTPException(status_code=403, detail="Forbidden")
    db["overlay"].delete_one({"_id": doc["_id"]})
    return {"status": "ok"}


# Widgets
@app.get("/overlays/{overlay_id}/widgets", response_model=List[Dict[str, Any]])
def list_widgets(overlay_id: str, user=Depends(get_current_user)):
    overlay = db["overlay"].find_one({"_id": overlay_id}) or db["overlay"].find_one({"_id": overlay_id})
    if not overlay:
        overlay = db["overlay"].find_one({"id": overlay_id})
    if not overlay:
        # try matching by owner and id string field created earlier
        overlay = db["overlay"].find_one({"owner_user_id": str(user["_id"]), "_id": overlay_id})
    if not overlay:
        raise HTTPException(status_code=404, detail="Overlay not found")
    if overlay.get("owner_user_id") != str(user["_id"]):
        # TODO: check editor permissions
        raise HTTPException(status_code=403, detail="Forbidden")

    docs = list(db["widget"].find({"overlay_id": overlay_id}))
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return docs


@app.post("/widgets", response_model=Dict[str, Any])
def create_widget(payload: CreateWidgetRequest, user=Depends(get_current_user)):
    if not can_use_widget_type(user, payload.type):
        raise HTTPException(status_code=402, detail="Upgrade plan to use this widget")
    widget = Widget(**payload.model_dump())
    widget_id = create_document("widget", widget)
    return {"id": widget_id}


@app.patch("/widgets/{widget_id}", response_model=Dict[str, Any])
def update_widget(widget_id: str, payload: UpdateWidgetRequest, user=Depends(get_current_user)):
    doc = db["widget"].find_one({"_id": widget_id}) or db["widget"].find_one({"id": widget_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Widget not found")
    # Authorization: ensure overlay belongs to user
    overlay = db["overlay"].find_one({"_id": doc.get("overlay_id")}) or db["overlay"].find_one({"id": doc.get("overlay_id")})
    if not overlay or overlay.get("owner_user_id") != str(user["_id"]):
        raise HTTPException(status_code=403, detail="Forbidden")

    db["widget"].update_one({"_id": doc["_id"]}, {"$set": payload.updates})
    return {"status": "ok"}


# Public overlay read-only endpoint for OBS browser source
@app.get("/o/{overlay_id}/{secret}", response_model=Dict[str, Any])
def get_overlay_public(overlay_id: str, secret: str):
    overlay = db["overlay"].find_one({"_id": overlay_id}) or db["overlay"].find_one({"id": overlay_id})
    if not overlay or overlay.get("secret_token") != secret:
        raise HTTPException(status_code=404, detail="Not found")
    widgets = list(db["widget"].find({"overlay_id": overlay_id}))
    for w in widgets:
        w["id"] = str(w.pop("_id"))
    overlay_resp = {
        "id": str(overlay.get("_id", overlay.get("id"))),
        "name": overlay.get("name"),
        "width": overlay.get("width"),
        "height": overlay.get("height"),
        "widgets": widgets,
    }
    return overlay_resp


# i18n messages endpoint (en/es)
I18N_MESSAGES = {
    "en": {
        "title": "Stream Overlays",
        "create_overlay": "Create Overlay",
        "overlay_url": "Overlay URL",
        "copy": "Copy",
        "save": "Save",
        "preview": "Preview",
        "sign_in": "Sign in",
    },
    "es": {
        "title": "Superposiciones de Stream",
        "create_overlay": "Crear Superposición",
        "overlay_url": "URL de Superposición",
        "copy": "Copiar",
        "save": "Guardar",
        "preview": "Vista previa",
        "sign_in": "Iniciar sesión",
    },
}


@app.get("/i18n/{locale}")
def get_i18n(locale: str):
    return I18N_MESSAGES.get(locale, I18N_MESSAGES["en"])


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
