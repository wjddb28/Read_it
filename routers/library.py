"""Authenticated endpoints for a user's private reading library."""
import json
import logging
import re
from datetime import date, datetime
from typing import Literal

import pymysql
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common import get_mysql_connection
from routers.auth import current_user
from routers.books import add_to_db

router = APIRouter(prefix="/api/library", tags=["library"])
logger = logging.getLogger("uvicorn.error")
ISBN_PATTERN = re.compile(r"^(978|979)\d{10}$")
BOOK_COLUMNS = """b.isbn, b.title, b.author, b.publisher, b.publish_year,
                  b.description, b.cover_image_url"""


class AddBook(BaseModel):
    isbn: str = Field(pattern=r"^(978|979)\d{10}$")


class ReadingUpdate(BaseModel):
    status: Literal["WISH", "READING", "COMPLETED"]
    startDate: date | None = None
    endDate: date | None = None
    rating: int = Field(default=0, ge=0, le=5)
    review: str = Field(default="", max_length=3000)
    logs: dict[str, str] = Field(default_factory=dict)


def connection():
    try:
        return get_mysql_connection()
    except (SystemExit, pymysql.MySQLError) as exc:
        logger.exception("Could not connect to MySQL for library")
        raise HTTPException(503, "서재를 불러오지 못했어요. 잠시 후 다시 시도해주세요.") from exc


def db_user_id(cursor, user):
    identity = user.get("id", "")
    if not identity.startswith("google:"):
        raise HTTPException(401, "로그인 후 이용해주세요.")
    cursor.execute("SELECT user_id FROM users WHERE google_id = %s", (identity[7:],))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(401, "로그인 후 이용해주세요.")
    return row["user_id"]


def fetch_record(cursor, user_id, isbn):
    cursor.execute(
        f"""SELECT r.isbn, r.status, r.start_date, r.end_date, r.rating,
                   r.review, r.logs, {BOOK_COLUMNS}
            FROM reading_record r JOIN book b ON b.isbn = r.isbn
            WHERE r.user_id = %s AND r.isbn = %s""",
        (user_id, isbn),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return serialize_record(row)


def serialize_record(row):
    logs = row["logs"]
    if isinstance(logs, str):
        try:
            logs = json.loads(logs)
        except json.JSONDecodeError as exc:
            logger.exception("Invalid calendar memo JSON for library record")
            raise HTTPException(500, "서재 기록을 읽지 못했어요.") from exc
    return {
        "id": row["isbn"],
        "book": {key: row[key] for key in (
            "isbn", "title", "author", "publisher", "publish_year",
            "description", "cover_image_url",
        )},
        "status": row["status"],
        "startDate": row["start_date"].isoformat() if row["start_date"] else "",
        "endDate": row["end_date"].isoformat() if row["end_date"] else "",
        "rating": int(row["rating"] or 0),
        "review": row["review"] or "",
        "logs": logs or {},
    }


def validate_update(payload):
    if payload.startDate and payload.endDate and payload.endDate < payload.startDate:
        raise HTTPException(422, "완독일은 시작일 이후로 선택해주세요.")
    for day, memo in payload.logs.items():
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(422, "독서 메모 날짜 형식이 올바르지 않아요.") from exc
        if len(memo) > 3000:
            raise HTTPException(422, "독서 메모는 3000자까지 저장할 수 있어요.")


@router.get("")
def get_library(user=Depends(current_user)):
    print("get library called")
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                f"""SELECT r.isbn, r.status, r.start_date, r.end_date, r.rating,
                           r.review, r.logs, {BOOK_COLUMNS}
                    FROM reading_record r JOIN book b ON b.isbn = r.isbn
                    WHERE r.user_id = %s ORDER BY r.record_id""",
                (user_id,),
            )
            records = [serialize_record(row) for row in cursor.fetchall()]
        return {"records": records}
    except pymysql.MySQLError as exc:
        logger.exception("Could not load MySQL library records")
        raise HTTPException(503, "서재를 불러오지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()


@router.post("")
def add_library_book(payload: AddBook, user=Depends(current_user)):
    print("add library book called")
    if not ISBN_PATTERN.fullmatch(payload.isbn):
        raise HTTPException(422, "ISBN 정보를 확인해주세요.")
    try:
        isbn = add_to_db(payload.isbn)
    except (SystemExit, pymysql.MySQLError) as exc:
        logger.exception("Could not ensure MySQL book for library")
        raise HTTPException(503, "책 정보를 저장하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                f"INSERT INTO reading_record (user_id, isbn) VALUES (%s, %s)",
                (user_id, isbn),
            )
            conn.commit()
            record = fetch_record(cursor, user_id, isbn)
        return {"record": record}
    except pymysql.err.IntegrityError as exc:
        conn.rollback()
        if exc.args and exc.args[0] == 1062:
            raise HTTPException(409, "이미 서재에 담긴 책이에요.") from exc
        logger.exception("Could not add MySQL library record")
        raise HTTPException(503, "책을 서재에 저장하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    except pymysql.MySQLError as exc:
        conn.rollback()
        logger.exception("Could not add MySQL library record")
        raise HTTPException(503, "책을 서재에 저장하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()


@router.put("/{isbn}")
def update_library_book(isbn: str, payload: ReadingUpdate, user=Depends(current_user)):
    print("update library book called")
    if not ISBN_PATTERN.fullmatch(isbn):
        raise HTTPException(422, "ISBN 정보를 확인해주세요.")
    validate_update(payload)
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                f"""UPDATE reading_record
                   SET status = %s, start_date = %s, end_date = %s, rating = %s,
                       review = %s, logs = %s
                   WHERE user_id = %s AND isbn = %s""",
                (
                    payload.status, payload.startDate, payload.endDate,
                    payload.rating or None, payload.review or None,
                    json.dumps(payload.logs, ensure_ascii=False),
                    user_id, isbn,
                ),
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    f"SELECT 1 FROM reading_record WHERE user_id = %s AND isbn = %s",
                    (user_id, isbn),
                )
                if not cursor.fetchone():
                    raise HTTPException(404, "서재에서 책을 찾을 수 없어요.")
            conn.commit()
            record = fetch_record(cursor, user_id, isbn)
        return {"record": record}
    except pymysql.MySQLError as exc:
        conn.rollback()
        logger.exception("Could not update MySQL library record")
        raise HTTPException(503, "독서 기록을 저장하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()


@router.delete("/{isbn}")
def remove_library_book(isbn: str, user=Depends(current_user)):
    print("remove library book called")
    if not ISBN_PATTERN.fullmatch(isbn):
        raise HTTPException(422, "ISBN 정보를 확인해주세요.")
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                "DELETE FROM reading_record WHERE user_id = %s AND isbn = %s",
                (user_id, isbn),
            )
            if cursor.rowcount == 0:
                raise HTTPException(404, "서재에서 책을 찾을 수 없어요.")
            conn.commit()
        return {"ok": True}
    except pymysql.MySQLError as exc:
        conn.rollback()
        logger.exception("Could not delete MySQL library record")
        raise HTTPException(503, "책을 서재에서 삭제하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()
