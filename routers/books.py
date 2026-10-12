from datetime import date, timedelta
from functools import lru_cache
from typing import Literal

import requests
from fastapi import APIRouter, HTTPException, Query

from common import get_mysql_connection
from fetch_books import EXCLUDED_AUDIENCE, api_get, build_record, clean_author, clean_title, to_int
from genre_map import kdc_to_genre

router = APIRouter(prefix="/api/books", tags=["books"])

SEARCH_PARAM = {"title": "title", "author": "author", "isbn": "isbn13", "keyword": "keyword"}
# 책 카드에 쓰는 공통 필드 (DB에서 꺼내는 API는 모두 이 모양으로 돌려준다)
CARD_COLUMNS = "isbn, title, author, publisher, publish_year, description, cover_image_url"


def safe_reason(e):
    """화면에 보낼 오류 이유. requests 오류 메시지엔 API 키가 든 URL이 있어 종류만 알려준다."""
    return str(e) if isinstance(e, RuntimeError) else type(e).__name__


def work_key(title, author):
    return title.replace(" ", ""), author


@router.get("/search")
def search_books(
    q: str = Query(min_length=1, description="검색어"),
    by: Literal["title", "author", "isbn", "keyword"] = "title",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
):
    """정보나루에서 실시간 검색. 같은 작품의 판본은 하나로 묶고,
    우리 DB에 이미 있는 작품이면 in_db=true + DB의 ISBN으로 바꿔서 돌려준다."""
    try:
        data = api_get("srchBooks", timeout=5, pageNo=page, pageSize=size, **{SEARCH_PARAM[by]: q})
    except (requests.RequestException, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=f"정보나루 검색 실패: {safe_reason(e)}") from e

    books, seen = [], set()
    for doc in (d["doc"] for d in data.get("docs", [])):
        if not (doc.get("isbn13") or "").startswith(("978", "979")):
            continue  # 978/979가 아니면 책이 아님 (DVD·음반 등)
        title, author = clean_title(doc.get("bookname")), clean_author(doc.get("authors"))
        if work_key(title, author) in seen:
            continue
        seen.add(work_key(title, author))
        books.append({
            "isbn": doc.get("isbn13"),
            "title": title,
            "author": author,
            "publisher": doc.get("publisher"),
            "publish_year": to_int(doc.get("publication_year")),
            "cover_image_url": doc.get("bookImageURL"),
            "in_db": False,
        })

    if books:
        conn = get_mysql_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT isbn, REPLACE(title, ' ', '') AS t, author FROM book
                       WHERE isbn IN %s OR REPLACE(title, ' ', '') IN %s""",
                    ([b["isbn"] for b in books], [work_key(b["title"], b["author"])[0] for b in books]),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        db_isbns = {r["isbn"] for r in rows}
        db_works = {(r["t"], r["author"]): r["isbn"] for r in rows}
        for b in books:
            db_isbn = b["isbn"] if b["isbn"] in db_isbns else db_works.get(work_key(b["title"], b["author"]))
            if db_isbn:
                b.update(isbn=db_isbn, in_db=True)

    return {"query": q, "total": to_int(data.get("numFound")) or 0, "books": books}


@lru_cache(maxsize=1)  # ponytail: 날짜별로 한 번만 정보나루 호출 (서버 메모리 캐시)
def _popular_30d(today):
    end = date.fromisoformat(today) - timedelta(days=1)
    start = end - timedelta(days=29)
    data = api_get("loanItemSrch", timeout=5, startDt=start.isoformat(), endDt=end.isoformat(), pageSize=100)
    books = []
    for doc in (d["doc"] for d in data.get("docs", [])):
        # 시드 수집과 같은 기준: 책(978/979)만, 학습참고서·아동 제외
        if not (doc.get("isbn13") or "").startswith(("978", "979")):
            continue
        if (doc.get("addition_symbol") or "").strip()[:1] in EXCLUDED_AUDIENCE:
            continue
        books.append({
            "ranking": len(books) + 1,
            "isbn": doc.get("isbn13"),
            "title": clean_title(doc.get("bookname")),
            "author": clean_author(doc.get("authors")),
            "publisher": doc.get("publisher"),
            "publish_year": to_int(doc.get("publication_year")),
            "cover_image_url": doc.get("bookImageURL"),
        })
    return {"start": start.isoformat(), "end": end.isoformat(), "books": books}


@router.get("/popular")
def popular_books(limit: int = Query(10, ge=1, le=50)):
    """최근 30일 정보나루 인기 대출 도서 (어제까지). ('/{isbn}'보다 먼저 선언해야 함)"""
    try:
        res = _popular_30d(date.today().isoformat())
    except (requests.RequestException, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=f"정보나루 인기 도서 조회 실패: {safe_reason(e)}") from e
    return {**res, "books": res["books"][:limit]}


@router.get("/{isbn}")
def book_detail(isbn: str):
    """도서 상세. 우리 DB에 있으면 DB에서, 없으면 정보나루에서 가져온다 (DB에 저장하지는 않음)."""
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT b.isbn, b.title, b.author, b.publisher, b.publish_year, b.description,
                          b.cover_image_url, b.kdc_class_name, g.name AS genre
                   FROM book b LEFT JOIN genre g USING (genre_id) WHERE b.isbn = %s""",
                (isbn,),
            )
            book = cur.fetchone()
            if book:
                cur.execute("SELECT word FROM book_keyword WHERE isbn = %s ORDER BY weight DESC LIMIT 10", (isbn,))
                return {**book, "keywords": [r["word"] for r in cur.fetchall()], "in_db": True}
    finally:
        conn.close()

    try:
        usage = api_get("usageAnalysisList", timeout=5, isbn13=isbn)
    except RuntimeError as e:  # 정보나루가 오류로 응답 (없는 ISBN 포함)
        raise HTTPException(status_code=404 if "ISBN" in str(e) else 502, detail=f"정보나루 조회 실패: {e}")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"정보나루 조회 실패: {safe_reason(e)}") from e
    if not usage.get("book", {}).get("bookname"):
        raise HTTPException(status_code=404, detail="도서를 찾을 수 없습니다.")
    b = build_record(isbn, {}, usage)
    return {
        "isbn": isbn, "title": b["title"], "author": b["author"], "publisher": b["publisher"],
        "publish_year": b["publish_year"], "description": b["description"],
        "cover_image_url": b["cover_image_url"], "kdc_class_name": b["kdc_class_name"],
        "genre": kdc_to_genre(b["kdc_class_no"]),
        "keywords": [k["word"] for k in b["keywords"][:10]], "in_db": False,
    }
    

def add_to_db(book: dict):
    #현재 아직 호출 X
    """정보나루에서 가져온 책 정보를 DB에 저장. 이미 있으면 업데이트 시도."""
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM book WHERE isbn = %s", (book["isbn"],))
            if cur.fetchone():
                #업데이트 시도
                cur.execute("""UPDATE book SET title=%s, author=%s, publisher=%s, publish_year=%s, description=%s,
                               cover_image_url=%s, kdc_class_name=%s, genre_id=(SELECT genre_id FROM genre WHERE name=%s) WHERE isbn=%s""",
                            (book["title"], book["author"], book["publisher"], book["publish_year"], book.get("description"), book.get("cover_image_url"), book.get("kdc_class_name"),
                             kdc_to_genre(book.get("kdc_class_no")), book["isbn"]))
                for kw in book.get("keywords", []):
                    cur.execute(
                        "UPDATE book_keyword SET weight=%s WHERE isbn=%s AND word=%s",
                        (kw["weight"], book["isbn"], kw["word"]),)
            else:
                #신규 저장
                cur.execute(
                    """INSERT INTO book (isbn, title, author, publisher, publish_year, description,
                                     cover_image_url, kdc_class_name, genre_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                           (SELECT genre_id FROM genre WHERE name = %s))""",
                    (book["isbn"], book["title"], book["author"], book["publisher"], book["publish_year"],
                    book.get("description"), book.get("cover_image_url"), book.get("kdc_class_name"),
                    kdc_to_genre(book.get("kdc_class_no"))),
                    )
                for kw in book.get("keywords", []):
                    cur.execute(
                    "INSERT INTO book_keyword (isbn, word, weight) VALUES (%s, %s, %s)",
                    (book["isbn"], kw["word"], kw["weight"]),
                    )
            conn.commit()
    except conn.interface.Error as e:
        print(f"DB 저장 실패: {e}")
        conn.close()
        return False
    except conn.integrity_error as e:
        print(f"DB 저장 실패 (무결성 오류): {e}")
        conn.close()
        return False
    finally:
        conn.close()
        return True