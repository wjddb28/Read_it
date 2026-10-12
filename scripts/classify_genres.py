"""
문학 도서(소설·에세이·시·희곡·기타 문학)에 상세 장르를 Gemini로 1~3개씩 붙여 seed/books.jsonl 의 "subgenres" 에 저장.
이미 붙은 책은 건너뛰므로 중간에 멈춰도 다시 실행하면 이어서 합니다. books.jsonl 갱신이라 main 브랜치에서 실행.

사용 예:
    python scripts/classify_genres.py --sample 50   # 50권만 분류해서 결과만 출력 (저장 안 함)
    python scripts/classify_genres.py               # 전체 분류 후 저장 → python scripts/load_seed.py
"""
import argparse
import json
from typing import Literal

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from common import BOOKS_JSONL, env
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, help="이 권수만 분류해 출력하고 저장하지 않음")
    args = parser.parse_args()

    books = [json.loads(line) for line in BOOKS_JSONL.open(encoding="utf-8") if line.strip()]
    todo = [b for b in books if kdc_to_genre(b.get("kdc_class_no")) in LITERATURE and "subgenres" not in b]
    if args.sample:
        todo = todo[::max(1, len(todo) // args.sample)][:args.sample]  # 장르가 고르게 섞이도록 띄엄띄엄
    print(f"분류 대상 {len(todo)}권")

    client = genai.Client(api_key=env("GEMINI_API_KEY"),
                          http_options=types.HttpOptions(timeout=90_000, retry_options=types.HttpRetryOptions(attempts=1)))
    done = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        result = classify(client, batch)
        for b in batch:
            if b["isbn"] not in result:
                continue
            done += 1
            if args.sample:
                print(f"  [{kdc_to_genre(b['kdc_class_no'])}] {b['title']} / {b['author']} → {', '.join(result[b['isbn']])}")
            else:
                b["subgenres"] = result[b["isbn"]]
        if not args.sample:  # 배치마다 저장해서 중간에 멈춰도 이어서 할 수 있게
            with BOOKS_JSONL.open("w", encoding="utf-8") as f:
                f.writelines(json.dumps(b, ensure_ascii=False) + "\n" for b in books)
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)} 처리, 분류됨 {done}권")

    print(f"완료: {done}/{len(todo)}권 분류" + ("" if args.sample else f" → {BOOKS_JSONL}"))
    if done < len(todo):
        print("분류 안 된 책은 다시 실행하면 이어서 처리합니다.")


if __name__ == "__main__":
    main()
