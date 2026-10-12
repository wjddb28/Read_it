"""
문학 도서(소설·에세이·시·희곡·기타 문학)에 상세 장르를 Gemini로 1~3개씩 붙입니다.
- 시드 도서: seed/books.jsonl 의 "subgenres" 에 저장 (books.jsonl 갱신이라 main 브랜치에서 실행)
- 서재 담기 등으로 DB에만 들어온 책: ensure_book() 이 저장할 때 classify_one() 으로 바로 분류.
  그때 Gemini가 실패해 장르가 빈 책은 --db 로 나중에 채움
이미 붙은 책은 건너뛰므로 중간에 멈춰도 다시 실행하면 이어서 합니다.

사용 예:
    python scripts/classify_genres.py --sample 50   # 50권만 분류해서 결과만 출력 (저장 안 함)
    python scripts/classify_genres.py               # 시드 전체 분류 후 저장 → python scripts/load_seed.py
    python scripts/classify_genres.py --db          # DB에만 있는 책 중 장르가 빈 문학 책을 분류해 DB에 저장
"""
import argparse
import json
import os
from functools import lru_cache
from typing import Literal

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from common import BOOKS_JSONL, get_mysql_connection
from genre_map import ESSAY_SUBGENRES, FICTION_SUBGENRES, LITERATURE, SUBGENRES, kdc_to_genre

MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]  # ai.py 와 같은 순서 (실패 시 다음 모델)
BATCH = 50


class Result(BaseModel):
    isbn: str
    subgenres: list[Literal[tuple(SUBGENRES)]]


PROMPT = f"""아래 도서 목록의 각 책에 상세 장르를 1~3개 붙여줘. 주어진 정보만 근거로 판단해.
- 이야기가 있는 책(소설·희곡)은 이 중에서: {", ".join(FICTION_SUBGENRES)}
- 에세이·시·산문·르포는 이 중에서: {", ".join(ESSAY_SUBGENRES)}
- 가장 잘 맞는 것부터 순서대로, 확실하지 않으면 1개만.
- 모든 책의 isbn을 그대로 돌려줘.

도서 목록(JSON):
"""


@lru_cache(maxsize=2)
def make_client(timeout_ms):
    """GEMINI_API_KEY 가 없으면 None (서재 담기는 분류 없이 계속 진행)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    return genai.Client(api_key=key, http_options=types.HttpOptions(
        timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1)))


def is_literature(b):
    return kdc_to_genre(b.get("kdc_class_no")) in LITERATURE


def book_brief(b):
    skip = {b["title"], b["author"]}
    words = [k["word"] for k in b["keywords"] if k["word"] not in skip][:8]
    return {"isbn": b["isbn"], "title": b["title"], "author": b["author"],
            "kdc": kdc_to_genre(b.get("kdc_class_no")), "description": (b["description"] or "")[:300],
            "keywords": words}


def classify(client, batch):
    """{isbn: [장르, ...]}. 두 모델 다 실패하면 빈 dict (그 책들은 다음 실행 때 다시)."""
    contents = PROMPT + json.dumps([book_brief(b) for b in batch], ensure_ascii=False)
    config = types.GenerateContentConfig(
        response_mime_type="application/json", response_schema=list[Result],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    for model in MODELS:
        try:
            parsed = client.models.generate_content(model=model, contents=contents, config=config).parsed
        except (errors.APIError, httpx.HTTPError) as e:
            print(f"  Gemini 실패 ({model}): {e}")
            continue
        wanted = {b["isbn"] for b in batch}
        # 목록에 없는 isbn·중복 장르는 버리고 최대 3개
        return {r.isbn: list(dict.fromkeys(r.subgenres))[:3] for r in parsed or [] if r.isbn in wanted and r.subgenres}
    return {}


def classify_one(b):
    """책 1권 (build_record 형태)의 상세 장르. 문학이 아니거나 실패하면 [] — 책 저장은 막지 않는다."""
    client = make_client(15_000)
    if not client or not is_literature(b):
        return []
    try:
        return classify(client, [b]).get(b["isbn"], [])
    except Exception as e:  # 응답 형식 오류 등 무엇이든 서재 담기를 실패시키지 않음
        print(f"상세 장르 분류 실패 ({b['isbn']}): {e}")
        return []


def db_todo():
    """DB에만 있는(시드가 아닌) 문학 책 중 상세 장르가 없는 책."""
    seed = {json.loads(line)["isbn"] for line in BOOKS_JSONL.open(encoding="utf-8") if line.strip()}
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT isbn, title, author, description, kdc_class_no FROM book b
                           WHERE NOT EXISTS (SELECT 1 FROM book_subgenre s WHERE s.isbn = b.isbn)""")
            books = [b for b in cur.fetchall() if b["isbn"] not in seed and is_literature(b)]
            for b in books:
                cur.execute("SELECT word FROM book_keyword WHERE isbn=%s ORDER BY weight DESC", (b["isbn"],))
                b["keywords"] = cur.fetchall()
    finally:
        conn.close()
    return books


def save_db(result):
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT genre_id, name FROM genre")
            ids = {r["name"]: r["genre_id"] for r in cur.fetchall()}
            cur.executemany("INSERT IGNORE INTO book_subgenre (isbn, genre_id) VALUES (%s, %s)",
                            [(isbn, ids[name]) for isbn, names in result.items() for name in names if name in ids])
        conn.commit()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, help="이 권수만 분류해 출력하고 저장하지 않음")
    parser.add_argument("--db", action="store_true", help="books.jsonl 대신 DB에만 있는 책을 분류해 DB에 저장")
    args = parser.parse_args()

    client = make_client(90_000)
    if not client:
        raise SystemExit(".env 에 GEMINI_API_KEY 값이 없습니다. .env.example 을 참고하세요.")

    books = [] if args.db else [json.loads(line) for line in BOOKS_JSONL.open(encoding="utf-8") if line.strip()]
    todo = db_todo() if args.db else [b for b in books if is_literature(b) and "subgenres" not in b]
    if args.sample:
        todo = todo[::max(1, len(todo) // args.sample)][:args.sample]  # 장르가 고르게 섞이도록 띄엄띄엄
    print(f"분류 대상 {len(todo)}권")

    done = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        result = classify(client, batch)
        done += len(result)
        if args.sample:
            for b in batch:
                if b["isbn"] in result:
                    print(f"  [{kdc_to_genre(b['kdc_class_no'])}] {b['title']} / {b['author']} → {', '.join(result[b['isbn']])}")
        elif args.db:
            save_db(result)
        else:  # 배치마다 저장해서 중간에 멈춰도 이어서 할 수 있게
            for b in batch:
                if b["isbn"] in result:
                    b["subgenres"] = result[b["isbn"]]
            with BOOKS_JSONL.open("w", encoding="utf-8") as f:
                f.writelines(json.dumps(b, ensure_ascii=False) + "\n" for b in books)
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)} 처리, 분류됨 {done}권")

    print(f"완료: {done}/{len(todo)}권 분류")
    if done < len(todo):
        print("분류 안 된 책은 다시 실행하면 이어서 처리합니다.")


if __name__ == "__main__":
    main()
