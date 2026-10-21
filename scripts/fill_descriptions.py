"""
줄거리가 없는 시드 도서에 국립중앙도서관 책소개를 채워 seed/books.jsonl 에 저장합니다. (수집 담당자만, main 브랜치에서)
.env 에 NL_API_KEY(국립중앙도서관 Open API 인증키)가 있어야 합니다. 팀원은 키 없이 git pull + load_seed 만 하면 됩니다.

사용 예:
    python scripts/fill_descriptions.py --dry-run   # 찾은 책소개를 출력만 (저장 안 함)
    python scripts/fill_descriptions.py             # 저장 → python scripts/load_seed.py (임베딩 다시 생성)
"""
import argparse
import json
import os

import requests

from common import BOOKS_JSONL, RAW_DIR
from fetch_books import nl_description


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    args = parser.parse_args()
    if not os.environ.get("NL_API_KEY"):
        raise SystemExit(".env 에 NL_API_KEY(국립중앙도서관 인증키)를 넣어주세요.")

    books = [json.loads(line) for line in BOOKS_JSONL.open(encoding="utf-8") if line.strip()]
    todo = [b for b in books if not b["description"]]
    print(f"줄거리 없는 책 {len(todo)}권")
    (RAW_DIR / "nl").mkdir(parents=True, exist_ok=True)
    filled = 0
    for b in todo:
        path = RAW_DIR / "nl" / f"{b['isbn']}.json"  # 찾은 책소개만 캐시 (못 찾은 책은 다음 실행 때 다시 조회)
        try:
            text = json.loads(path.read_text(encoding="utf-8")) if path.exists() else nl_description(b["isbn"])
        except RuntimeError as e:  # 인증키 오류 등 → 계속해도 전부 실패하므로 멈춤
            raise SystemExit(str(e))
        except (requests.RequestException, ValueError) as e:
            print(f"  [건너뜀] {b['title']}: {type(e).__name__}")
            continue
        if text and not path.exists():
            path.write_text(json.dumps(text, ensure_ascii=False), encoding="utf-8")
        if text:
            filled += 1
            print(f"  {b['title']} → {text[:60]}…")
            b["description"], b["description_source"] = text, "nl"  # 출처 표시 (정보나루가 아닌 국립중앙도서관)
    print(f"채운 책 {filled}/{len(todo)}권")
    if filled and not args.dry_run:
        tmp = BOOKS_JSONL.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(b, ensure_ascii=False) + "\n" for b in books), encoding="utf-8")
        os.replace(tmp, BOOKS_JSONL)
        print(f"저장: {BOOKS_JSONL} → python scripts/load_seed.py 로 DB·임베딩에 반영하세요.")


if __name__ == "__main__":
    main()
