"""사용자 프로필 관련"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import pymysql

from common import get_mysql_connection
from routers.auth import current_user
from routers.library import db_user_id

router = APIRouter(prefix="/api/profile", tags=["profile"])
logger = logging.getLogger("uvicorn.error")


class ProfileUpdate(BaseModel):
    nickname: str = Field(..., min_length=2, max_length=20)
    about_me: str | None = Field(default=None, max_length=200)
    gender: str | None = Field(default=None, pattern="^(M|F|N)$")
    birth_year: int | None = Field(default=None, ge=1900, le=2100)


def connection(error_message: str):
    try:
        return get_mysql_connection()
    except (SystemExit, pymysql.MySQLError) as exc:
        logger.exception("Could not connect to MySQL for profile")
        raise HTTPException(503, error_message) from exc


def fetch_profile(cursor, user_id: int) -> dict[str, str | None]:
    cursor.execute(
        "SELECT nickname, about_me, gender, birth_year FROM users WHERE user_id = %s",
        (user_id,),
    )
    profile = cursor.fetchone()
    if not profile:
        raise HTTPException(404, "사용자 프로필을 찾을 수 없어요.")
    return {
        "nickname": profile["nickname"],
        "about_me": profile["about_me"],
        "gender": profile["gender"],
        "birth_year": profile["birth_year"]
    }


def fetch_library_stats(cursor, user_id: int) -> dict[str, int]:
    cursor.execute(
        """SELECT COUNT(*) AS total_books,
                  COALESCE(SUM(status = 'COMPLETED'), 0) AS completed_books,
                  (SELECT COALESCE(SUM(d.reading_minutes), 0)
                   FROM daily_reading_log d
                   JOIN reading_record r ON r.record_id = d.record_id
                   WHERE r.user_id = %s) AS total_reading_minutes
           FROM reading_record
           WHERE user_id = %s""",
        (user_id, user_id),
    )
    stats = cursor.fetchone()
    return {
        "total_books": int(stats["total_books"]),
        "completed_books": int(stats["completed_books"]),
        "total_reading_minutes": int(stats["total_reading_minutes"]),
    }


def fetch_profile_data(cursor, user_id: int) -> dict:
    return {
        **fetch_profile(cursor, user_id),
        "stats": fetch_library_stats(cursor, user_id),
    }


@router.put("/update")
def update_profile(payload: ProfileUpdate, user=Depends(current_user)):
    """사용자 프로필 업데이트"""
    if not payload.nickname:
        raise HTTPException(400, "닉네임은 공백일 수 없어요.")
    conn = connection("프로필을 업데이트하지 못했어요. 잠시 후 다시 시도해주세요.")
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                "UPDATE users SET nickname = %s, about_me = %s, gender = %s, birth_year = %s WHERE user_id = %s",
                (payload.nickname, payload.about_me, payload.gender, payload.birth_year, user_id),
            )
            profile = fetch_profile_data(cursor, user_id)
            conn.commit()
            return {"message": "프로필이 업데이트되었습니다.", **profile}
    except pymysql.MySQLError as exc:
        conn.rollback()
        logger.exception("Could not update user profile in MySQL")
        raise HTTPException(503, "프로필을 업데이트하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()


@router.get("/me")
def get_profile(user=Depends(current_user)) -> dict:
    """사용자 프로필 조회"""
    print("get_profile called")
    conn = connection("프로필을 가져오지 못했어요. 잠시 후 다시 시도해주세요.")
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            return fetch_profile_data(cursor, user_id)
    except pymysql.MySQLError as exc:
        logger.exception("Could not fetch user profile from MySQL")
        raise HTTPException(503, "프로필을 가져오지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()


@router.get("/other/{user_id}")
def get_other_profile(user_id: int) -> dict[str, str | None]:
    """다른 사용자 프로필 조회"""
    conn = connection("프로필을 가져오지 못했어요. 잠시 후 다시 시도해주세요.")
    try:
        with conn.cursor() as cursor:
            return fetch_profile(cursor, user_id)
    except pymysql.MySQLError as exc:
        logger.exception("Could not fetch other user profile from MySQL")
        raise HTTPException(503, "프로필을 가져오지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()