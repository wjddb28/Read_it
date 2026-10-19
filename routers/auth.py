"""Google sign-in endpoints and in-memory login sessions."""
import hashlib
import logging
import os
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field
import pymysql

from common import get_mysql_connection

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


def persist_google_user(google_id, email, nickname):
    try:
        conn = get_mysql_connection()
    except SystemExit as exc:
        raise HTTPException(503, "MySQL 로그인 저장 설정이 올바르지 않아요.") from exc
    except pymysql.MySQLError as exc:
        logging.getLogger("uvicorn.error").exception("Could not connect to MySQL for login")
        raise HTTPException(503, "로그인 정보를 저장하지 못했어요. 잠시 후 다시 시도해주세요.") from exc

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM users WHERE google_id = %s", (google_id,))
            user = cursor.fetchone()
            if user:
                cursor.execute(
                    "UPDATE users SET email = %s, nickname = %s WHERE user_id = %s",
                    (email, nickname, user["user_id"]),
                )
            else:
                cursor.execute(
                    "INSERT INTO users (email, google_id, nickname) VALUES (%s, %s, %s)",
                    (email, google_id, nickname),
                )
                user = {"user_id": cursor.lastrowid}
        conn.commit()
        return user["user_id"]
    except pymysql.err.IntegrityError as exc:
        conn.rollback()
        raise HTTPException(409, "이 이메일은 이미 다른 계정에 연결되어 있어요.") from exc
    except pymysql.MySQLError as exc:
        conn.rollback()
        logging.getLogger("uvicorn.error").exception("Could not save Google login to MySQL")
        raise HTTPException(503, "로그인 정보를 저장하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()


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
    google_id = info["sub"]
    nickname = (info.get("name") or "독자")[:32]
    email = info.get("email")
    persist_google_user(google_id, email, nickname)
    user = {"id": "google:" + google_id, "nickname": nickname, "email": email}
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
