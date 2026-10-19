"""
AI 추천 검색(/api/search?ai=true)의 정확도를 eval/questions.jsonl 로 채점합니다.
고도화 전후를 같은 질문·같은 DB로 돌려 비교하세요.

사용 예:
    python scripts/eval_search.py --name baseline           # 채점 후 eval/results/baseline.json 저장
    python scripts/eval_search.py --compare baseline after   # 두 결과를 나란히 비교

질문 종류 (eval/questions.jsonl 의 type)
    book     : 정답 책(isbn, 여러 권 인정하려면 리스트) → Hit@5(상위 5권 안에 있나), MRR(1/정답 순위)
    genre    : 포함 장르(include) → 장르 정확도@5 (상위 5권 중 그 장르가 붙은 책 비율)
    negative : 포함+제외 장르 → 장르 정확도@5 (포함 O, 제외 X 인 책 비율), 위반율 (제외 장르가 섞인 책 비율)
    similar  : "○○와 비슷한 책" (기준 책 base_isbn) → 장르 일치@5 (기준 책과 세부 장르가 하나라도 같은 책 비율),
               본인·같은 작가 포함률 (질문한 책 자신이나 같은 작가 책이 섞인 비율, 낮을수록 좋음)
               ※ 함께 대출된 책은 추천 가산점에 쓰므로 정답으로 쓰지 않음 (점수가 부풀지 않게)
split: dev 는 고도화를 조정할 때 보는 질문, test 는 마지막 비교에만 쓰는 질문.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from common import get_mysql_connection  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.jsonl"
RESULTS = ROOT / "eval" / "results"
TOP_K = 5
METRICS = [("hit@5", "book", "Hit@5"), ("mrr", "book", "MRR"), ("genre@5", "genre", "장르 정확도@5 (장르)"),
           ("neg_genre@5", "negative", "장르 정확도@5 (부정)"), ("violation", "negative", "위반율 (낮을수록 좋음)"),
           ("sim_genre@5", "similar", "장르 일치@5 (비슷한 책)"), ("sim_self", "similar", "본인·같은 작가 포함률 (낮을수록)"),
           ("latency", None, "평균 응답(초)")]


def subgenres(isbns):
    if not isbns:
        return {}
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT s.isbn, g.name FROM book_subgenre s JOIN genre g ON g.genre_id = s.genre_id
                           WHERE s.isbn IN %s""", (isbns,))
            out = {}
            for r in cur.fetchall():
                out.setdefault(r["isbn"], set()).add(r["name"])
            return out
    finally:
        conn.close()


def score(q, books, genres):
    isbns = [b["isbn"] for b in books]
    if q["type"] == "book":
        golds = q["isbn"] if isinstance(q["isbn"], list) else [q["isbn"]]  # 정답으로 인정할 책이 여러 권이면 리스트
        rank = next((i + 1 for i, isbn in enumerate(isbns) if isbn in golds), None)
        return {"rank": rank, "hit@5": float(rank is not None), "mrr": 1 / rank if rank else 0.0}
    if q["type"] == "similar":
        base = genres.get(q["base_isbn"], set())
        same = [b["isbn"] == q["base_isbn"] or b["author"] == q["base_author"] for b in books]
        return {"sim_genre@5": sum(bool(genres.get(i, set()) & base) for i in isbns) / TOP_K,
                "sim_self": sum(same) / max(len(books), 1)}
    inc, exc = set(q["include"]), set(q["exclude"])
    good = [bool(genres.get(i, set()) & inc) and not genres.get(i, set()) & exc for i in isbns]
    bad = [bool(genres.get(i, set()) & exc) for i in isbns]
    precision = sum(good) / TOP_K  # 5권보다 적게 나오면 모자란 만큼 틀린 것으로 계산
    if q["type"] == "genre":
        return {"genre@5": precision}
    return {"neg_genre@5": precision, "violation": sum(bad) / max(len(isbns), 1)}


def run(name):
    from routers.search import smart_search  # 임베딩 모델 로딩이 무거워서 채점할 때만

    questions = [json.loads(line) for line in QUESTIONS.open(encoding="utf-8") if line.strip()]
    smart_search(q="워밍업 질문 잔잔한 소설", ai=True, top_k=TOP_K, comment=False)  # 첫 호출 로딩 시간은 제외
    details = []
    for q in questions:
        start = time.perf_counter()
        res = smart_search(q=q["query"], ai=True, top_k=TOP_K, comment=False)
        latency = time.perf_counter() - start
        books = res.get("books", []) if res["mode"] == "ai" else []  # retry(엉뚱한 입력 판정)면 결과 없음으로 채점
        genres = subgenres([b["isbn"] for b in books] + [q.get("base_isbn")] * ("base_isbn" in q))
        details.append({**q, "mode": res["mode"], "latency": latency, **score(q, books, genres),
                        "results": [{"isbn": b["isbn"], "title": b["title"],
                                     "subgenres": sorted(genres.get(b["isbn"], []))} for b in books]})
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {path}\n")
    print_table({name: details})
    misses = [d for d in details if d.get("hit@5") == 0.0
              or d.get("genre@5", d.get("neg_genre@5", d.get("sim_genre@5", 1))) < 0.6]
    print(f"\n틀렸거나 장르 정확도 60% 미만인 질문 {len(misses)}개:")
    for d in misses:
        got = ", ".join(r["title"] for r in d["results"][:3])
        print(f"  [{d['id']} {d['split']}] {d['query']}  → {got}")


def summarize(details, split):
    rows = [d for d in details if split == "all" or d["split"] == split]
    out = {}
    for key, qtype, _ in METRICS:
        vals = [d[key] for d in rows if (qtype is None or d["type"] == qtype) and key in d]
        out[key] = sum(vals) / len(vals) if vals else None
    return out


def print_table(runs):
    for split in ("test", "dev", "all"):
        sums = {n: summarize(d, split) for n, d in runs.items()}
        count = len([d for d in next(iter(runs.values())) if split == "all" or d["split"] == split])
        print(f"[{split}] 질문 {count}개")
        print(f"  {'지표':<24}" + "".join(f"{n:>12}" for n in runs))
        for key, _, label in METRICS:
            cells = []
            for n in runs:
                v = sums[n][key]
                cells.append(f"{'-':>12}" if v is None else f"{v:>12.2f}" if key in ("mrr", "latency") else f"{v:>11.0%} ")
            print(f"  {label:<24}" + "".join(cells))
        print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", help="이 이름으로 채점 결과 저장 (예: baseline)")
    parser.add_argument("--compare", nargs="+", help="저장된 결과 이름들을 나란히 비교")
    args = parser.parse_args()
    if args.compare:
        print_table({n: json.loads((RESULTS / f"{n}.json").read_text(encoding="utf-8")) for n in args.compare})
    elif args.name:
        run(args.name)
    else:
        parser.error("--name 또는 --compare 가 필요합니다.")


if __name__ == "__main__":
    main()
