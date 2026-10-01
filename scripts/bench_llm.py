"""
추천 코멘트용 Gemini 모델별 응답 시간 측정.
실제 /api/recommend 와 같은 방식으로 프롬프트를 만들고(벡터 검색 상위 3권), 모델마다 같은 프롬프트를 보낸다.

    python scripts/bench_llm.py --rounds 2 > bench.json
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from ai import book_collection, embed_model  # noqa: E402
from common import env, get_mysql_connection  # noqa: E402

MODELS = ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.8-flash",
          "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
QUERIES = ["비 오는 날 읽기 좋은 위로가 되는 소설", "노후 준비를 위한 배당 투자", "소름 돋는 반전이 있는 추리 스릴러"]


def build_prompt(query):
    """routers/recommend.py 와 같은 프롬프트"""
    ids = book_collection.query(query_embeddings=[embed_model.encode(query).tolist()], n_results=3)["ids"][0]
    conn = get_mysql_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT isbn, title, author, description FROM book WHERE isbn IN %s", (ids,))
        books = sorted(cur.fetchall(), key=lambda b: ids.index(b["isbn"]))
    conn.close()
    context = "\n".join(f"- {b['title']} (저자: {b['author']}): {b['description'][:100]}..." for b in books)
    return f"""
        사용자 질문: {query}
        검색된 도서 목록:
        {context}

        위 도서 정보를 바탕으로 사용자에게 각 책을 추천하는 다정한 코멘트를 300자 이내로 작성해줘.
        """, [b["title"] for b in books]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()

    # 재시도 없이 1회 호출, 60초 넘으면 실패로 기록
    client = genai.Client(api_key=env("GEMINI_API_KEY"),
                          http_options=types.HttpOptions(timeout=60_000,
                                                         retry_options=types.HttpRetryOptions(attempts=1)))
    config = types.GenerateContentConfig(
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    prompts = [(q, *build_prompt(q)) for q in QUERIES]

    results = []
    for rnd in range(args.rounds):
        for query, prompt, titles in prompts:
            for model in MODELS:  # 모델을 번갈아 호출해 시간대 차이가 한 모델에 몰리지 않게
                t = time.perf_counter()
                row = {"round": rnd + 1, "query": query, "model": model}
                try:
                    text = client.models.generate_content(model=model, contents=prompt, config=config).text or ""
                    row.update(ok=True, sec=round(time.perf_counter() - t, 2), chars=len(text),
                               mentions_only_results=all(t in text for t in titles))
                except Exception as e:  # noqa: BLE001 - 실패 사유를 그대로 기록
                    row.update(ok=False, sec=round(time.perf_counter() - t, 2), error=str(e)[:60])
                print(json.dumps(row, ensure_ascii=False), file=sys.stderr)
                results.append(row)
    print(json.dumps({"measured_at": datetime.now().isoformat(timespec="minutes"), "results": results},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
