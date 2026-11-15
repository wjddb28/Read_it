"""사용자 프로필 관련"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import pymysql

from common import get_mysql_connection
from routers.auth import check_origin, current_user
from routers.community_store import key
from routers.library import db_user_id

router = APIRouter(prefix="/api/profile", tags=["profile"])
logger = logging.getLogger("uvicorn.error")


class ProfileUpdate(BaseModel):
    nickname: str = Field(..., min_length=2, max_length=20)
    about_me: str | None = Field(default=None, max_length=200)
    gender: str | None = Field(default=None, pattern="^(M|F|N)$")
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    likedGenres: list[str] = Field(default_factory=list, max_length=40)
    dislikedGenres: list[str] = Field(default_factory=list, max_length=40)
    onboarded: bool = True


def connection(error_message: str):
    try:
        return get_mysql_connection()
    except (SystemExit, pymysql.MySQLError) as exc:
        logger.exception("Could not connect to MySQL for profile")
        raise HTTPException(503, error_message) from exc


def fetch_profile(cursor, user_id: int) -> dict:
    cursor.execute(
        """SELECT public_id, nickname, about_me, gender, birth_year, onboarded
           FROM users WHERE user_id = %s""",
        (user_id,),
    )
    profile = cursor.fetchone()
    if not profile:
        raise HTTPException(404, "사용자 프로필을 찾을 수 없어요.")
    return {
        "profileId": profile["public_id"],
        "nickname": profile["nickname"],
        "about_me": profile["about_me"],
        "bio": profile["about_me"] or "",
        "gender": profile["gender"],
        "birth_year": profile["birth_year"],
        "onboarded": bool(profile["onboarded"]),
    }


def fetch_genre_preferences(cursor, user_id: int) -> dict[str, list[str]]:
    cursor.execute(
        """SELECT g.name, fg.preference
           FROM favorite_genre fg
           JOIN genre g ON g.genre_id = fg.genre_id
           WHERE fg.user_id = %s
           ORDER BY g.name""",
        (user_id,),
    )
    preferences = {"likedGenres": [], "dislikedGenres": []}
    for row in cursor.fetchall():
        preferences["likedGenres" if row["preference"] == "LIKE" else "dislikedGenres"].append(
            row["name"]
        )
    return preferences


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
        **fetch_genre_preferences(cursor, user_id),
        "stats": fetch_library_stats(cursor, user_id),
    }


def clean_genres(values: list[str]) -> list[str]:
    cleaned = []
    seen = set()
    for value in values:
        genre = value.strip()
        if not genre or len(genre) > 30:
            raise HTTPException(422, "장르는 1~30자로 입력해주세요.")
        normalized = key(genre)
        if normalized not in seen:
            cleaned.append(genre)
            seen.add(normalized)
    return cleaned


@router.put("/update", dependencies=[Depends(check_origin)])
def update_profile(payload: ProfileUpdate, user=Depends(current_user)):
    """사용자 프로필 업데이트"""
    nickname = payload.nickname.strip()
    if len(nickname) < 2 or any(ord(char) < 32 for char in nickname):
        raise HTTPException(400, "닉네임은 공백일 수 없어요.")
    liked = clean_genres(payload.likedGenres)
    disliked = clean_genres(payload.dislikedGenres)
    if {key(genre) for genre in liked} & {key(genre) for genre in disliked}:
        raise HTTPException(422, "같은 장르를 선호·비선호에 동시에 선택할 수 없어요.")

    conn = connection("프로필을 업데이트하지 못했어요. 잠시 후 다시 시도해주세요.")
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                """UPDATE users
                   SET nickname = %s, nickname_key = %s, about_me = %s, gender = %s,
                       birth_year = %s, onboarded = %s
                   WHERE user_id = %s""",
                (
                    nickname,
                    key(nickname),
                    (payload.about_me or "").strip(),
                    payload.gender,
                    payload.birth_year,
                    payload.onboarded,
                    user_id,
                ),
            )
            preferences = [(name, "LIKE") for name in liked]
            preferences.extend((name, "DISLIKE") for name in disliked)
            genre_ids = []
            for name, preference in preferences:
                cursor.execute(
                    "INSERT IGNORE INTO genre (name, parent_id) VALUES (%s, NULL)",
                    (name,),
                )
                cursor.execute("SELECT genre_id FROM genre WHERE name = %s", (name,))
                row = cursor.fetchone()
                if not row: raise HTTPException(422, "장르를 추가할 수 없었어요.")
                genre_ids.append((user_id, row["genre_id"], preference))
            cursor.execute("DELETE FROM favorite_genre WHERE user_id = %s", (user_id,))
            if genre_ids:
                cursor.executemany(
                    """INSERT INTO favorite_genre (user_id, genre_id, preference)
                       VALUES (%s, %s, %s)""",
                    genre_ids,
                )
            profile = fetch_profile_data(cursor, user_id)
            conn.commit()
            return {"message": "프로필이 업데이트되었습니다.", **profile}
    except pymysql.err.IntegrityError as exc:
        conn.rollback()
        raise HTTPException(409, "이미 사용 중인 닉네임이에요.") from exc
    except pymysql.MySQLError as exc:
        conn.rollback()
        logger.exception("Could not update user profile in MySQL")
        raise HTTPException(503, "프로필을 업데이트하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()


@router.get("/me")
def get_profile(user=Depends(current_user)) -> dict:
    """사용자 프로필 조회"""
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