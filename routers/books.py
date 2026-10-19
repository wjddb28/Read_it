import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import lru_cache
from typing import Literal

import requests
from fastapi import APIRouter, HTTPException, Query

from book_store import ensure_book
from common import get_mysql_connection
from fetch_books import EXCLUDED_AUDIENCE, api_get, build_record, clean_author, clean_title, to_int
from genre_map import kdc_to_genre

router = APIRouter(prefix="/api/books", tags=["books"])

SEARCH_PARAM = {"title": "title", "author": "author", "isbn": "isbn13", "keyword": "keyword"}
# 책 카드에 쓰는 공통 필드 (DB에서 꺼내는 API는 모두 이 모양으로 돌려준다)
CARD_COLUMNS = "isbn, title, author, publisher, publish_year, description, cover_image_url, loan_count"


def safe_reason(e):
    """화면에 보낼 오류 이유. requests 오류 메시지엔 API 키가 든 URL이 있어 종류만 알려준다."""
    return str(e) if isinstance(e, RuntimeError) else type(e).__name__


def work_key(title, author):
    return title.replace(" ", ""), author


@router.get("/search")
def search_books(
    q: str = Query(min_length=1, description="검색어"),
    by: Literal["all", "title", "author", "isbn", "keyword"] = "title",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
):
    """정보나루에서 실시간 검색. 같은 작품의 판본은 하나로 묶고,
    우리 DB에 이미 있는 작품이면 in_db=true + DB의 ISBN으로 바꿔서 돌려준다.
    by=all 은 제목·저자·키워드 검색을 동시에 보내 합친다 (겹치는 책이 있어 total 은 추정치)."""
    if by == "all":
        with ThreadPoolExecutor(3) as ex:
            parts = list(ex.map(lambda b: search_books(q=q, by=b, page=page, size=size), ("title", "author", "keyword")))
        books, seen = [], set()
        for b in (b for part in parts for b in part["books"]):  # 제목 → 저자 → 키워드 순서로 우선
            key = work_key(b["title"], b["author"])
            if b["isbn"] not in seen and key not in seen:
                seen.update((b["isbn"], key))
                books.append(b)
        return {"query": q, "total": sum(p["total"] for p in parts), "total_is_estimate": True,
                "total_pages": max(math.ceil(p["total"] / size) for p in parts), "books": books,
                "corrected_query": next((p["corrected_query"] for p in parts if p.get("corrected_query")), None)}
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
            "loan_count": to_int(doc.get("loan_count")),
            "cover_image_url": doc.get("bookImageURL"),
            "in_db": False,
        })

    if books:
        conn = get_mysql_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT isbn, REPLACE(title, ' ', '') AS t, author, description, loan_count FROM book
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
                local = next((r for r in rows if r["isbn"] == db_isbn), {})
                b["description"] = local.get("description")
                if b.get("loan_count") is None:
                    b["loan_count"] = local.get("loan_count")

    if not books and by != "isbn":
        # 정보나루는 띄어쓰기에 민감함 ('앨리스죽이기' 0건). 우리 DB에서 띄어쓰기를 무시하고 같은 제목·저자를 찾아
        # 올바른 표기로 다시 검색하고, 그래도 없으면 DB의 그 책을 돌려준다
        fixed, local = db_spelling(q, by)
        if fixed and fixed != q:
            res = search_books(q=fixed, by=by, page=page, size=size)
            if res["books"]:
                return {**res, "query": q, "corrected_query": fixed}
        if local:
            return {"query": q, "corrected_query": fixed if fixed != q else None, "total": len(local), "books": local}

    return {"query": q, "total": to_int(data.get("numFound")) or 0, "books": books}


def db_spelling(q, by):
    """(DB에 있는 올바른 표기, 그 표기의 책 목록). 띄어쓰기만 다른 제목(저자 검색이면 저자)이 없으면 (None, [])"""
    col = "author" if by == "author" else "title"
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"""SELECT isbn, title, author, publisher, publish_year, cover_image_url, description, loan_count, {col} AS v FROM book
                            WHERE REPLACE({col}, ' ', '') = %s ORDER BY loan_count DESC LIMIT 20""", (q.replace(" ", ""),))
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return None, []
    return rows[0]["v"], [{**{k: r[k] for k in r if k != "v"}, "in_db": True} for r in rows]


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
            "loan_count": to_int(doc.get("loan_count")),
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
                book["keywords"] = [r["word"] for r in cur.fetchall()]
                cur.execute("SELECT AVG(rating) AS average_rating, COUNT(*) AS review_count FROM book_review WHERE isbn = %s", (isbn,))
                summary = cur.fetchone() or {}
                cur.execute("""SELECT r.rating, r.content, r.created_at, r.has_spoiler, u.nickname
                               FROM book_review r JOIN users u ON u.user_id = r.user_id
                               WHERE r.isbn = %s ORDER BY r.created_at DESC LIMIT 50""", (isbn,))
                book.update(in_db=True, average_rating=summary.get("average_rating"),
                            review_count=summary.get("review_count", 0), reviews=cur.fetchall())
    finally:
        conn.close()

    if book and book.get("description"):
        return book
    try:
        usage = api_get("usageAnalysisList", timeout=5, isbn13=isbn)
    except RuntimeError as e:  # 정보나루가 오류로 응답 (없는 ISBN 포함)
        if book:
            return book
        raise HTTPException(status_code=404 if "ISBN" in str(e) else 502, detail=f"정보나루 조회 실패: {e}")
    except requests.RequestException as e:
        if book:
            return book
        raise HTTPException(status_code=502, detail=f"정보나루 조회 실패: {safe_reason(e)}") from e
    if not usage.get("book", {}).get("bookname"):
        if book:
            return book
        raise HTTPException(status_code=404, detail="도서를 찾을 수 없습니다.")
    b = build_record(isbn, {}, usage)
    if book:
        book["description"] = b.get("description") or ""
        if not book.get("keywords"):
            book["keywords"] = [k["word"] for k in b["keywords"][:10]]
        return book
    return {
        "isbn": isbn, "title": b["title"], "author": b["author"], "publisher": b["publisher"],
        "publish_year": b["publish_year"], "description": b["description"],
        "cover_image_url": b["cover_image_url"], "kdc_class_name": b["kdc_class_name"],
        "genre": kdc_to_genre(b["kdc_class_no"]),
        "keywords": [k["word"] for k in b["keywords"][:10]], "in_db": False,
        "average_rating": None, "review_count": 0, "reviews": [],
    }


def add_to_db(isbn: str) -> str:
    """서재 담기용: 책이 우리 DB에 있도록 보장하고, 서재에 연결할 ISBN을 돌려준다.
    DB에 없으면 정보나루에서 받아 MySQL + ChromaDB 에 저장 (문학이면 상세 장르도 분류).
    같은 작품의 다른 판본이 이미 있으면 그 ISBN을 돌려준다. 실제 저장은 scripts/book_store.py 의 ensure_book()."""
    from ai import book_collection, embed_model  # 임베딩 모델이 무거워서 쓸 때 로딩
    try:
        return ensure_book(isbn, embed_model, book_collection)
    except (LookupError, RuntimeError) as e:
        if isinstance(e, LookupError) or "ISBN" in str(e):  # 정보나루는 없는 ISBN을 오류로 응답
            raise HTTPException(status_code=404, detail="정보나루에서 찾을 수 없는 ISBN이에요.") from e
        raise HTTPException(status_code=502, detail=f"정보나루 조회 실패: {safe_reason(e)}") from e
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"정보나루 조회 실패: {safe_reason(e)}") from e