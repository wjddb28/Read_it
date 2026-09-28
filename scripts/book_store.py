"""
도서 1권을 MySQL + ChromaDB 에 저장하는 공통 코드.
- load_seed.py : 시드 도서를 한꺼번에 적재할 때
- ensure_book() : 서재 담기 등에서 DB에 없는 책을 그 자리에서 추가할 때
"""
from common import get_mysql_connection
from fetch_books import api_get, build_record
from genre_map import kdc_to_genre

BOOK_COLUMNS = ("isbn", "title", "author", "publisher", "publish_year", "description",
                "cover_image_url", "kdc_class_no", "kdc_class_name", "genre_id", "loan_count")


def genre_ids(cur):
    cur.execute("SELECT genre_id, name FROM genre")
    return {row["name"]: row["genre_id"] for row in cur.fetchall()}


def upsert_book(cur, b, genres):
    """book + book_keyword + book_relation 에 1권 저장 (이미 있으면 갱신)."""
    b["genre_id"] = genres.get(kdc_to_genre(b.get("kdc_class_no")))
    cur.execute(
        """INSERT INTO book (isbn, title, author, publisher, publish_year, description,
               cover_image_url, kdc_class_no, kdc_class_name, genre_id, loan_count)
           VALUES (%(isbn)s, %(title)s, %(author)s, %(publisher)s, %(publish_year)s,
               %(description)s, %(cover_image_url)s, %(kdc_class_no)s,
               %(kdc_class_name)s, %(genre_id)s, %(loan_count)s)
           ON DUPLICATE KEY UPDATE title=VALUES(title), author=VALUES(author),
               publisher=VALUES(publisher), publish_year=VALUES(publish_year),
               description=VALUES(description), cover_image_url=VALUES(cover_image_url),
               kdc_class_no=VALUES(kdc_class_no), kdc_class_name=VALUES(kdc_class_name),
               genre_id=VALUES(genre_id), loan_count=VALUES(loan_count)""",
        {k: b.get(k) for k in BOOK_COLUMNS},
    )
    cur.execute("DELETE FROM book_keyword WHERE isbn=%s", (b["isbn"],))
    cur.executemany(
        "INSERT INTO book_keyword (isbn, word, weight) VALUES (%s, %s, %s)",
        [(b["isbn"], k["word"][:50], k["weight"]) for k in b["keywords"]],
    )
    cur.execute("DELETE FROM book_relation WHERE isbn=%s", (b["isbn"],))
    relations = {}
    for key, rel_type in (("co_loan_books", "CO_LOAN"),
                          ("mania_rec_books", "RECOMMEND"),
                          ("reader_rec_books", "RECOMMEND")):
        for rank, r in enumerate(b[key]):
            relations.setdefault((r["isbn"], rel_type), 1.0 / (rank + 1))
    cur.executemany(
        """INSERT INTO book_relation (isbn, related_isbn, relation_type, score)
           VALUES (%s, %s, %s, %s)""",
        [(b["isbn"], isbn, t, s) for (isbn, t), s in relations.items()],
    )


def embedding_text(b):
    """제목 + 줄거리 + 핵심 키워드. (정보나루 줄거리는 평균 200자 내외로 짧아 키워드로 보강)
    검색 정확도 평가 후 조합을 바꿔볼 수 있는 튜닝 포인트."""
    skip = {b["title"], b["author"]}
    words = [k["word"] for k in b["keywords"] if k["word"] not in skip][:10]
    parts = [b["title"], b["description"], "키워드: " + ", ".join(words) if words else ""]
    return "\n".join(p for p in parts if p)


def chroma_metadata(b):
    return {"genre_id": b["genre_id"] or -1, "author": b["author"] or ""}


def find_same_work(cur, title, author):
    """제목(공백 무시)과 저자가 같은 책이 이미 있으면 그 ISBN. 다른 판본 중복 저장 방지."""
    cur.execute(
        "SELECT isbn FROM book WHERE REPLACE(title, ' ', '') = %s AND author = %s LIMIT 1",
        (title.replace(" ", ""), author),
    )
    row = cur.fetchone()
    return row["isbn"] if row else None


def ensure_book(isbn, embed_model, collection):
    """ISBN의 책이 DB에 있도록 보장하고, 실제로 쓸 ISBN을 돌려준다.
    - 이미 있으면 그대로
    - 같은 작품의 다른 판본이 있으면 그 ISBN
    - 없으면 정보나루에서 받아 MySQL 저장 → 임베딩해 Chroma 저장
    정보나루에 없는 ISBN이면 LookupError."""
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT isbn FROM book WHERE isbn=%s", (isbn,))
            if cur.fetchone():
                return isbn

            usage = api_get("usageAnalysisList", isbn13=isbn, timeout=5)
            if not usage.get("book", {}).get("bookname"):
                raise LookupError(f"정보나루에 없는 ISBN: {isbn}")
            b = build_record(isbn, {}, usage)

            existing = find_same_work(cur, b["title"], b["author"])
            if existing:
                return existing

            upsert_book(cur, b, genre_ids(cur))
        conn.commit()  # MySQL 먼저: Chroma가 실패해도 load_seed로 다시 만들 수 있음
    finally:
        conn.close()

    collection.upsert(
        ids=[b["isbn"]],
        embeddings=[embed_model.encode(embedding_text(b)).tolist()],
        metadatas=[chroma_metadata(b)],
    )
    return b["isbn"]
