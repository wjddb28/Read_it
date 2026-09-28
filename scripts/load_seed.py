"""
seed/books.jsonl 을 로컬 MySQL + ChromaDB 에 적재합니다. 팀원 각자 실행합니다.

사용 예:
    python scripts/load_seed.py            # 테이블 생성(없으면) + 도서 upsert + 임베딩
    python scripts/load_seed.py --reset    # 모든 테이블을 지우고 처음부터 (사용자/기록 데이터도 삭제됨!)
"""
import argparse
import json
import re

from common import BOOKS_JSONL, CHROMA_DIR, INIT_SQL, env, get_mysql_connection
from genre_map import GENRES, kdc_to_genre

EMBED_MODEL = "jhgan/ko-sbert-multitask"
COLLECTION = "books"
BOOK_COLUMNS = ("isbn", "title", "author", "publisher", "publish_year", "description",
                "cover_image_url", "kdc_class_no", "kdc_class_name", "genre_id", "loan_count")


def run_init_sql(reset):
    sql = INIT_SQL.read_text(encoding="utf-8")
    sql = re.sub(r"--[^\n]*", "", sql)  # 주석 제거 후 ; 기준 분리
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    db = env("MYSQL_DB", "read_it_db")

    conn = get_mysql_connection(with_db=False)
    try:
        with conn.cursor() as cur:
            if reset:
                cur.execute(f"DROP DATABASE IF EXISTS `{db}`")
                print(f"[reset] {db} 삭제")
            for stmt in statements:
                stmt = stmt.replace("read_it_db", db)
                stmt = re.sub(r"^CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", stmt)
                cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def load_genres(cur):
    ids = {}
    for name, parent in GENRES:  # 상위 장르가 항상 먼저 나오도록 정렬되어 있음
        cur.execute(
            """INSERT INTO genre (name, parent_id) VALUES (%s, %s)
               ON DUPLICATE KEY UPDATE parent_id=VALUES(parent_id)""",
            (name, ids.get(parent)),
        )
        cur.execute("SELECT genre_id FROM genre WHERE name=%s", (name,))
        ids[name] = cur.fetchone()["genre_id"]
    return ids


def load_books(books):
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            genre_ids = load_genres(cur)
            for b in books:
                b["genre_id"] = genre_ids.get(kdc_to_genre(b.get("kdc_class_no")))
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
        conn.commit()
    finally:
        conn.close()
    print(f"MySQL 적재 완료: 도서 {len(books)}권")


def embedding_text(b):
    """제목 + 줄거리 + 핵심 키워드. (정보나루 줄거리는 평균 200자 내외로 짧아 키워드로 보강)
    검색 정확도 평가 후 조합을 바꿔볼 수 있는 튜닝 포인트."""
    skip = {b["title"], b["author"]}
    words = [k["word"] for k in b["keywords"] if k["word"] not in skip][:10]
    parts = [b["title"], b["description"], "키워드: " + ", ".join(words) if words else ""]
    return "\n".join(p for p in parts if p)


def load_chroma(books):
    import chromadb
    from sentence_transformers import SentenceTransformer

    print(f"임베딩 모델 로딩: {EMBED_MODEL}")
    model = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    collection = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    vectors = model.encode([embedding_text(b) for b in books],
                           batch_size=32, show_progress_bar=True).tolist()
    collection.add(
        ids=[b["isbn"] for b in books],
        embeddings=vectors,
        metadatas=[{"genre_id": b["genre_id"] or -1, "author": b["author"] or ""} for b in books],
    )
    print(f"ChromaDB 적재 완료: {collection.count()}건 ({CHROMA_DIR})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="DB를 삭제하고 새로 만듦")
    args = parser.parse_args()

    books = [json.loads(line) for line in BOOKS_JSONL.open(encoding="utf-8") if line.strip()]
    run_init_sql(args.reset)
    load_books(books)
    load_chroma(books)


if __name__ == "__main__":
    main()
