from typing import Literal

import requests
from fastapi import APIRouter, HTTPException, Query

from common import get_mysql_connection
from fetch_books import api_get, build_record, clean_author, clean_title, to_int
from genre_map import kdc_to_genre

router = APIRouter(prefix="/api/books", tags=["books"])

SEARCH_PARAM = {"title": "title", "author": "author", "isbn": "isbn13", "keyword": "keyword"}


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
        raise HTTPException(status_code=502, detail=f"정보나루 검색 실패: {e}")

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
        raise HTTPException(status_code=502, detail=f"정보나루 조회 실패: {e}")
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
