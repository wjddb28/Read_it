"""
도서관 정보나루 API로 인기대출도서(베스트셀러)를 수집해 seed/books.jsonl 로 저장합니다.
수집 담당자 한 명만 실행하고, 결과 파일(books.jsonl)을 git에 커밋합니다.

- API 응답은 seed/raw/ 에 캐시되므로 다시 실행해도 이미 받은 책은 API를 호출하지 않습니다.
- IP 미등록 키는 하루 500회 제한이 있어 --max-calls 로 호출 수를 제한합니다.
  제한에 걸리면 다음 날 같은 명령을 다시 실행하면 이어서 수집합니다.

사용 예:
    python scripts/fetch_books.py --target 1000 --max-calls 450
"""
import argparse
import json
import re
import sys
import time
from datetime import date, timedelta

import requests

from common import BOOKS_JSONL, RAW_DIR, env

BASE_URL = "http://data4library.kr/api"

# ISBN 부가기호 첫 자리(독자 대상): 5,6 학습참고서 / 7 아동 → 제외
EXCLUDED_AUDIENCE = {"5", "6", "7"}


class QuotaExceeded(Exception):
    pass


def api_get(endpoint, timeout=20, **params):
    """정보나루 API 1회 호출. 서버(routers/books.py)도 이 함수를 쓴다."""
    params.update(authKey=env("LIBRARY_API_KEY"), format="json")
    resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json().get("response", {})
    if "error" in data:
        raise RuntimeError(f"{endpoint} 오류: {data['error']}")
    return data


class Client:
    """수집용: 호출 횟수를 세서 하루 한도를 넘지 않게 한다."""
    def __init__(self, max_calls):
        self.max_calls = max_calls
        self.calls = 0

    def get(self, endpoint, **params):
        if self.calls >= self.max_calls:
            raise QuotaExceeded
        self.calls += 1
        data = api_get(endpoint, **params)
        time.sleep(0.2)  # 서버 부담 완화
        return data


def cached(path, fetch):
    """캐시 파일이 있으면 읽고, 없으면 fetch() 결과를 저장한다."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def unwrap(items, key):
    """정보나루 JSON은 [{"doc": {...}}, ...] 형태로 한 번 감싸져 있다."""
    return [item[key] for item in items or [] if key in item]


def collect_popular_isbns(client, target, start_dt, end_dt):
    isbns, ranking, seen = [], {}, set()
    page = 1
    while len(isbns) < target:
        path = RAW_DIR / f"popular_{start_dt}_{end_dt}_p{page}.json"
        data = cached(path, lambda: client.get(
            "loanItemSrch", startDt=start_dt, endDt=end_dt, pageNo=page, pageSize=200))
        docs = unwrap(data.get("docs"), "doc")
        if not docs:
            break
        for doc in docs:
            isbn = doc.get("isbn13", "").strip()
            addition = (doc.get("addition_symbol") or "").strip()
            if len(isbn) != 13 or isbn in ranking:
                continue
            if addition[:1] in EXCLUDED_AUDIENCE:
                continue
            # 부가기호·KDC 둘 다 없는 항목은 대부분 아동 시리즈 낱권이라 제외
            if not addition and not (doc.get("class_no") or "").strip():
                continue
            # 같은 책의 다른 판본(ISBN만 다름)은 순위가 높은 것 하나만
            key = (clean_title(doc.get("bookname")).replace(" ", ""), clean_author(doc.get("authors")))
            if key in seen:
                continue
            seen.add(key)
            ranking[isbn] = doc
            isbns.append(isbn)
        page += 1
    return isbns[:target], ranking


def to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def clean_title(title):
    """'소년이 온다 :한강 장편소설' → '소년이 온다' (부제 제거)"""
    title = re.sub(r"^\([^)]*\)\s*", "", title or "")  # 앞머리 괄호 설명 제거
    title = re.split(r"\s*[:=/]|\s+-\s+", title)[0]
    return title.strip()


ROLE = r"(지은이|글쓴이|저자|글|그림|원작|각색|엮은이|편저?)"
AUTHOR_LABELS = re.compile(
    rf"{ROLE}(·{ROLE})*\s*:"       # '지은이:', '원작·각색:'
    rf"|[(\[]{ROLE}(·{ROLE})*[)\]]"  # '(지은이)', '[지음]'은 아래
    rf"|\[?지음\]?$|\s저$|\s{ROLE}(·{ROLE})*$"  # '지음', '[지음]', '글·그림'
)


def clean_author(author):
    """'지은이: 히가시노 게이고 ;옮긴이: 김윤경' → '히가시노 게이고' (역자·역할 표시 제거)"""
    first = (author or "").split(";")[0]
    first = ",".join(p for p in first.split(",") if "옮김" not in p and "옮긴이" not in p).strip()
    return re.sub(r"\s+", " ", AUTHOR_LABELS.sub("", first)).strip(" ,")


def related_books(items):
    return [
        {"isbn": b.get("isbn13"), "title": b.get("bookname")}
        for b in unwrap(items, "book") if b.get("isbn13")
    ]


def build_record(isbn, popular_doc, usage):
    book = usage.get("book", {})
    keywords = [
        {"word": k.get("word"), "weight": float(k.get("weight") or 0)}
        for k in unwrap(usage.get("keywords"), "keyword") if k.get("word")
    ]
    return {
        "isbn": isbn,
        "title": clean_title(book.get("bookname") or popular_doc.get("bookname")),
        "author": clean_author(book.get("authors") or popular_doc.get("authors")),
        "publisher": book.get("publisher") or popular_doc.get("publisher"),
        "publish_year": to_int(book.get("publication_year") or popular_doc.get("publication_year")),
        "description": (book.get("description") or "").strip(),
        "cover_image_url": book.get("bookImageURL") or popular_doc.get("bookImageURL"),
        "kdc_class_no": book.get("class_no") or popular_doc.get("class_no"),
        "kdc_class_name": book.get("class_nm") or popular_doc.get("class_nm"),
        "loan_count": to_int(popular_doc.get("loan_count")) or to_int(book.get("loanCnt")) or 0,
        "popular_rank": to_int(popular_doc.get("ranking")),
        "keywords": keywords,
        "co_loan_books": related_books(usage.get("coLoanBooks")),
        "mania_rec_books": related_books(usage.get("maniaRecBooks")),
        "reader_rec_books": related_books(usage.get("readerRecBooks")),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=1000, help="수집할 도서 수")
    parser.add_argument("--max-calls", type=int, default=450, help="이번 실행의 최대 API 호출 수")
    parser.add_argument("--days", type=int, default=365, help="인기대출 집계 기간(최근 N일)")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    client = Client(args.max_calls)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=args.days)

    records, pending = [], 0
    try:
        isbns, ranking = collect_popular_isbns(
            client, args.target, start.isoformat(), end.isoformat())
        print(f"인기대출 도서 {len(isbns)}권 확보, 상세정보 수집 시작")
        for i, isbn in enumerate(isbns, 1):
            path = RAW_DIR / f"usage_{isbn}.json"
            try:
                usage = cached(path, lambda: client.get("usageAnalysisList", isbn13=isbn))
            except QuotaExceeded:
                pending = len(isbns) - i + 1
                break
            except (requests.RequestException, RuntimeError) as e:
                print(f"  [건너뜀] {isbn}: {e}")
                continue
            records.append(build_record(isbn, ranking[isbn], usage))
            if i % 50 == 0:
                print(f"  {i}/{len(isbns)} (이번 실행 API 호출 {client.calls}회)")
    except QuotaExceeded:
        print("인기대출 목록 수집 중 호출 한도 도달")

    records.sort(key=lambda r: r["popular_rank"] or 10**9)
    with BOOKS_JSONL.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    no_desc = sum(1 for r in records if not r["description"])
    print(f"\n저장 완료: {BOOKS_JSONL} ({len(records)}권, 줄거리 없음 {no_desc}권)")
    print(f"이번 실행 API 호출: {client.calls}회")
    if pending:
        print(f"호출 한도로 {pending}권 남음 → 내일 같은 명령으로 다시 실행하면 이어서 수집합니다.")
        sys.exit(2)


if __name__ == "__main__":
    main()
