"""
seed/books.jsonl 을 로컬 MySQL + ChromaDB 에 적재합니다. 팀원 각자 실행합니다.

사용 예:
    python scripts/load_seed.py            # 테이블 생성(없으면) + 도서 upsert + 임베딩
    python scripts/load_seed.py --reset    # 모든 테이블을 지우고 처음부터 (사용자/기록 데이터도 삭제됨!)
"""
import argparse
import json
import re

from book_store import chroma_metadata, embedding_text, upsert_book
from common import BOOKS_JSONL, CHROMA_DIR, INIT_SQL, env, get_mysql_connection
from genre_map import GENRES

EMBED_MODEL = "jhgan/ko-sbert-multitask"
COLLECTION = "books"


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


# init.sql 의 CREATE TABLE 은 이미 있는 테이블에는 적용되지 않아서, 나중에 추가된 컬럼은 여기서 채운다.
# (테이블, 컬럼, ALTER 문) — init.sql 에 컬럼을 추가하면 여기에도 한 줄 추가
MIGRATIONS = [
    ("users", "email", "ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL UNIQUE AFTER password_hash"),
    ("users", "google_id", "ALTER TABLE users ADD COLUMN google_id VARCHAR(255) NULL UNIQUE AFTER email"),
    ("users", "about_me", "ALTER TABLE users ADD COLUMN about_me TEXT NULL AFTER nickname"),
    ("reading_record", "review", "ALTER TABLE reading_record ADD COLUMN review INT NULL AFTER end_date, "
                                 "ADD FOREIGN KEY (review) REFERENCES book_review(review_id) ON DELETE SET NULL"),
    ("reading_record", "logs", "ALTER TABLE reading_record ADD COLUMN logs TEXT NULL AFTER review"),
]
# 구글 로그인은 아이디·비밀번호가 없으므로 비워둘 수 있어야 함 (여러 번 실행해도 결과가 같음)
ALWAYS = [
    "ALTER TABLE users MODIFY login_id VARCHAR(32) NULL",
    "ALTER TABLE users MODIFY password_hash VARCHAR(255) NULL",
]


def migrate(cur):
    added = []
    for table, column, ddl in MIGRATIONS:
        cur.execute(f"SHOW COLUMNS FROM {table} LIKE %s", (column,))
        if not cur.fetchone():
            cur.execute(ddl)
            added.append(f"{table}.{column}")
    for ddl in ALWAYS:
        cur.execute(ddl)
    if added:
        print("DB 구조 갱신: " + ", ".join(added) + " 컬럼 추가")


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
            migrate(cur)
            genres = load_genres(cur)
            for b in books:
                upsert_book(cur, b, genres)
        conn.commit()
    finally:
        conn.close()
    print(f"MySQL 적재 완료: 도서 {len(books)}권")


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
        metadatas=[chroma_metadata(b) for b in books],
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
