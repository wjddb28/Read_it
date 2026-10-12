"""구글 인증 전용. MySQL/Chroma/SQL/파일 저장을 사용하지 않습니다."""
import hashlib
import os
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])
DEFAULT_CLIENT_ID = "731854853999-s5nee5kcd90g187nfekrnp9cbikbda5s.apps.googleusercontent.com"
COOKIE = "readit_google_session"
TTL = 86400
_sessions = {}
_lock = threading.Lock()

def client_id():
    return os.getenv("GOOGLE_CLIENT_ID", DEFAULT_CLIENT_ID)

def check_origin(request: Request):
    allowed = {x.strip() for x in os.getenv("READIT_AUTH_ORIGINS", "http://localhost:5173").split(",")}
    if request.headers.get("origin") not in allowed:
        raise HTTPException(403, "허용되지 않은 로그인 요청 출처예요.")

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(request: Request):
    key = digest(request.cookies.get(COOKIE, ""))
    with _lock:
        entry = _sessions.get(key)
        if not entry or entry["expires"] <= time.time():
            _sessions.pop(key, None)
            raise HTTPException(401, "로그인 후 이용해주세요.")
        return entry["user"].copy()

class GoogleLogin(BaseModel):
    credential: str = Field(min_length=1, max_length=12000)

@router.get("/config")
def config():
    return {"client_id": client_id()}

@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": user}

@router.post("/google", dependencies=[Depends(check_origin)])
def google_login(payload: GoogleLogin, request: Request, response: Response):
    try:
        info = id_token.verify_oauth2_token(payload.credential, GoogleRequest(), client_id())
        if not info.get("sub") or not info.get("email_verified"):
            raise ValueError("Unverified identity")
    except ValueError:
        raise HTTPException(401, "구글 인증이 유효하지 않아요. 다시 로그인해주세요.")
    except Exception:
        raise HTTPException(503, "구글 인증 서버에 연결하지 못했어요.")
    user = {"id": "google:" + info["sub"], "nickname": info.get("name") or "독자", "email": info.get("email")}
    token = secrets.token_urlsafe(32)
    with _lock:
        now = time.time()
        for key in list(_sessions):
            if _sessions[key]["expires"] <= now:
                del _sessions[key]
        _sessions.pop(digest(request.cookies.get(COOKIE, "")), None)
        _sessions[digest(token)] = {"user": user, "expires": now + TTL}
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=TTL,
                        secure=os.getenv("READIT_COOKIE_SECURE", "false").lower() == "true", path="/")
    return {"user": user}

@router.post("/logout", dependencies=[Depends(check_origin)])
def logout(request: Request, response: Response):
    with _lock:
        _sessions.pop(digest(request.cookies.get(COOKIE, "")), None)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}
