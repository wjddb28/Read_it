"""Authenticated endpoints for a user's private reading library."""
import logging
import re
from datetime import date
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


class DailyReadingLogUpdate(BaseModel):
    content: str | None = Field(default=None, max_length=3000)
    reading_minutes: int | None = Field(default=None, ge=0, le=32767)


class reviewUpdate(BaseModel):
    content: str = Field(default="", max_length=3000)
    star: int = Field(default=0, ge=0, le=5)
    has_spoiler: bool = Field(default=False)


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
        f"""SELECT r.record_id, r.isbn, r.status, r.start_date, r.end_date, {BOOK_COLUMNS}
            FROM reading_record r JOIN book b ON b.isbn = r.isbn
            WHERE r.user_id = %s AND r.isbn = %s""",
        (user_id, isbn),
    )
    row = cursor.fetchone()
    if not row:
        return None
    daily_logs = fetch_daily_logs(cursor, [row["record_id"]])
    return serialize_record(row, daily_logs.get(row["record_id"], {}))


def fetch_daily_logs(cursor, record_ids):
    if not record_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(record_ids))
    cursor.execute(
        f"""SELECT record_id, log_date, content, reading_minutes
            FROM daily_reading_log
            WHERE record_id IN ({placeholders})""",
        tuple(record_ids),
    )
    daily_logs = {}
    for row in cursor.fetchall():
        day = row["log_date"].isoformat()
        per_record = daily_logs.setdefault(row["record_id"], {"logs": {}, "readingMinutes": {}})
        per_record["logs"][day] = row["content"] or ""
        per_record["readingMinutes"][day] = int(row["reading_minutes"] or 0)
    return daily_logs


def serialize_record(row, daily_logs=None):
    daily_logs = daily_logs or {}
    return {
        "id": row["isbn"],
        "book": {key: row[key] for key in (
            "isbn", "title", "author", "publisher", "publish_year",
            "description", "cover_image_url",
        )},
        "status": row["status"],
        "startDate": row["start_date"].isoformat() if row["start_date"] else "",
        "endDate": row["end_date"].isoformat() if row["end_date"] else "",
        "logs": daily_logs.get("logs", {}),
        "readingMinutes": daily_logs.get("readingMinutes", {}),
    }


def validate_update(payload):
    if payload.startDate and payload.endDate and payload.endDate < payload.startDate:
        raise HTTPException(422, "완독일은 시작일 이후로 선택해주세요.")


@router.get("")
def get_library(user=Depends(current_user)):
    print("get library called")
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                f"""SELECT r.record_id, r.isbn, r.status, r.start_date, r.end_date, {BOOK_COLUMNS}
                    FROM reading_record r JOIN book b ON b.isbn = r.isbn
                    WHERE r.user_id = %s ORDER BY r.record_id""",
                (user_id,),
            )
            rows = cursor.fetchall()
            daily_logs = fetch_daily_logs(cursor, [row["record_id"] for row in rows])
            records = [
                serialize_record(row, daily_logs.get(row["record_id"], {}))
                for row in rows
            ]
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
                   SET status = %s, start_date = %s, end_date = %s
                   WHERE user_id = %s AND isbn = %s""",
                (
                    payload.status, payload.startDate, payload.endDate, user_id, isbn,
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


@router.put("/{isbn}/logs/{log_date}")
def update_daily_reading_log(
    isbn: str,
    log_date: date,
    payload: DailyReadingLogUpdate,
    user=Depends(current_user),
):
    if not ISBN_PATTERN.fullmatch(isbn):
        raise HTTPException(422, "ISBN 정보를 확인해주세요.")
    if not (payload.content or "").strip() and not payload.reading_minutes:
        raise HTTPException(422, "독서 메모나 읽은 시간을 입력해주세요.")
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                "SELECT record_id FROM reading_record WHERE user_id = %s AND isbn = %s",
                (user_id, isbn),
            )
            reading_record = cursor.fetchone()
            if not reading_record:
                raise HTTPException(404, "서재에서 책을 찾을 수 없어요.")

            cursor.execute(
                """INSERT INTO daily_reading_log
                       (record_id, log_date, content, reading_minutes)
                   VALUES (%s, %s, %s, COALESCE(%s, 0))
                   ON DUPLICATE KEY UPDATE
                       content = IF(%s IS NULL, content, VALUES(content)),
                       reading_minutes = IF(%s IS NULL, reading_minutes, VALUES(reading_minutes))""",
                (
                    reading_record["record_id"], log_date,
                    (payload.content.strip() or None) if payload.content is not None else None,
                    payload.reading_minutes, payload.content,
                    payload.reading_minutes,
                ),
            )
            conn.commit()
            record = fetch_record(cursor, user_id, isbn)
        return {"record": record}
    except pymysql.MySQLError as exc:
        conn.rollback()
        logger.exception("Could not save MySQL daily reading log")
        raise HTTPException(503, "독서 기록을 저장하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()

@router.get("/{isbn}/logs")
def get_daily_reading_logs(isbn: str, user=Depends(current_user), date: date | None = None):
    if not ISBN_PATTERN.fullmatch(isbn):
        raise HTTPException(422, "ISBN 정보를 확인해주세요.")
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                "SELECT record_id FROM reading_record WHERE user_id = %s AND isbn = %s",
                (user_id, isbn),
            )
            reading_record = cursor.fetchone()
            if not reading_record:
                raise HTTPException(404, "서재에서 책을 찾을 수 없어요.")

            if date:
                cursor.execute(
                    """SELECT log_date, content, reading_minutes
                       FROM daily_reading_log
                       WHERE record_id = %s AND log_date = %s""",
                    (reading_record["record_id"], date),
                )
                row = cursor.fetchone()
                if not row:
                    return {"log": None}
                return {
                    "log": {
                        "date": row["log_date"].isoformat(),
                        "content": row["content"] or "",
                        "readingMinutes": int(row["reading_minutes"] or 0),
                    }
                }
            else:
                cursor.execute(
                    """SELECT log_date, content, reading_minutes
                       FROM daily_reading_log
                       WHERE record_id = %s""",
                    (reading_record["record_id"],),
                )
                logs = {}
                for row in cursor.fetchall():
                    logs[row["log_date"].isoformat()] = {
                        "content": row["content"] or "",
                        "readingMinutes": int(row["reading_minutes"] or 0),
                    }
                return {"logs": logs}
    except pymysql.MySQLError as exc:
        logger.exception("Could not fetch MySQL daily reading logs")
        raise HTTPException(503, "독서 기록을 불러오지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()

@router.delete("/{isbn}/logs/{log_date}")
def delete_daily_reading_log(isbn: str, log_date: date, user=Depends(current_user)):
    if not ISBN_PATTERN.fullmatch(isbn):
        raise HTTPException(422, "ISBN 정보를 확인해주세요.")
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                """UPDATE daily_reading_log d
                   JOIN reading_record r ON r.record_id = d.record_id
                   SET d.content = NULL
                   WHERE r.user_id = %s AND r.isbn = %s AND d.log_date = %s""",
                (user_id, isbn, log_date),
            )
            cursor.execute(
                """DELETE d FROM daily_reading_log d
                   JOIN reading_record r ON r.record_id = d.record_id
                   WHERE r.user_id = %s AND r.isbn = %s AND d.log_date = %s
                       AND d.reading_minutes = 0""",
                (user_id, isbn, log_date),
            )
            cursor.execute(
                "SELECT 1 FROM reading_record WHERE user_id = %s AND isbn = %s",
                (user_id, isbn),
            )
            if not cursor.fetchone():
                raise HTTPException(404, "서재에서 책을 찾을 수 없어요.")
            conn.commit()
            record = fetch_record(cursor, user_id, isbn)
        return {"record": record}
    except pymysql.MySQLError as exc:
        conn.rollback()
        logger.exception("Could not delete MySQL daily reading log")
        raise HTTPException(503, "독서 기록을 삭제하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
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

@router.put("/{isbn}/review")        
def review_book(isbn: str, payload: reviewUpdate, user=Depends(current_user)):
    if not ISBN_PATTERN.fullmatch(isbn):
        raise HTTPException(422, "ISBN 정보를 확인해주세요.")
    content = payload.content.strip()
    if not payload.star and content:
        raise HTTPException(422, "코멘트를 저장하려면 평점을 선택해주세요.")
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                "SELECT 1 FROM reading_record WHERE user_id = %s AND isbn = %s",
                (user_id, isbn),
            )
            if not cursor.fetchone():
                raise HTTPException(404, "서재에서 책을 찾을 수 없어요.")

            if payload.star:
                cursor.execute(
                    """INSERT INTO book_review (user_id, isbn, content, rating, has_spoiler)
                       VALUES (%s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE content = VALUES(content),
                           rating = VALUES(rating), has_spoiler = VALUES(has_spoiler)""",
                    (user_id, isbn, content or None, payload.star, payload.has_spoiler),
                )
            else:
                cursor.execute(
                    "DELETE FROM book_review WHERE user_id = %s AND isbn = %s",
                    (user_id, isbn),
                )
            conn.commit()
            record = fetch_record(cursor, user_id, isbn)
            if record is None:
                raise HTTPException(404, "서재에서 책을 찾을 수 없어요.")
            record["rating"] = payload.star
            record["content"] = content
        return {"record": record}
    except pymysql.MySQLError as exc:
        conn.rollback()
        logger.exception("Could not update MySQL library review")
        raise HTTPException(503, "리뷰를 저장하지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()


@router.get("/{isbn}/review")
def get_book_review(isbn: str, user=Depends(current_user)):
    if not ISBN_PATTERN.fullmatch(isbn):
        raise HTTPException(422, "ISBN 정보를 확인해주세요.")
    conn = connection()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                "SELECT content, rating, has_spoiler FROM book_review WHERE user_id = %s AND isbn = %s",
                (user_id, isbn),
            )
            review = cursor.fetchone()
            if not review:
                return {"content": "", "rating": 0, "has_spoiler": False}
            return {
                "content": review["content"] or "",
                "rating": int(review["rating"] or 0),
                "has_spoiler": bool(review["has_spoiler"]),
            }
    except pymysql.MySQLError as exc:
        logger.exception("Could not fetch MySQL library review")
        raise HTTPException(503, "리뷰를 불러오지 못했어요. 잠시 후 다시 시도해주세요.") from exc
    finally:
        conn.close()