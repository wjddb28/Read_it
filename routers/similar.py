"""'○○와 비슷한 책' 질문 처리: 질문 속 책을 찾아 그 책을 기준으로 추천한다.
- 추천 목록: 그 책의 줄거리 벡터와 비슷한 책 + 같은 세부 장르·함께 대출된 책에 가산점. 같은 작가의 책은 빼고
- 시리즈(제목이 기준 책 제목으로 시작) + 같은 작가의 책은 same_author 로 따로 돌려준다 (한 작가·시리즈로 추천이 채워지지 않게)
"""
import re

import numpy as np
from fastapi import HTTPException

from ai import book_collection
from common import get_mysql_connection
from routers.books import CARD_COLUMNS, add_to_db, search_books, work_key

# 'X와 비슷한 책', 'X 같은 따뜻한 소설', 'X 같은 판타지 추천' — 뒤에 꾸미는 말이 두 단어까지 와도 됨
SIMILAR_RE = re.compile(r"^[\s『「《<\"']*(.+?)[\s』」》>\"']*(?:이랑|랑|와|과|하고)?\s*(?:비슷한|유사한|같은|닮은)\s*"
                        r"(?:\S+\s+){0,2}?\S*(?:책|도서|소설|작품|에세이|시집|만화|판타지|거|것|추천)")
MAX_PER_AUTHOR = 2  # 추천 목록이 한 작가 책으로 채워지지 않게
# ponytail: 가산점은 감으로 정한 값. 평가셋 dev 질문으로 조정
GENRE_BONUS = 0.05     # 세부 장르가 하나라도 같으면 (세부 장르가 없는 책은 같은 KDC 장르면)
RELATION_BONUS = 0.10  # 정보나루 '함께 대출된 책·추천 도서'에 있으면
CANDIDATES = 30


def title_in_query(q):
    """'앨리스 죽이기와 비슷한 책 추천해줘' → '앨리스 죽이기'. 패턴이 아니면 None"""
    m = SIMILAR_RE.match(q)
    return m.group(1).strip() if m else None


def find_book(title):
    """제목(띄어쓰기 무시)이 같은 책. DB에 없으면 정보나루에서 찾아 저장한다. 못 찾으면 None"""
    key = title.replace(" ", "")
    sql = "SELECT isbn, title, author, genre_id FROM book WHERE {} ORDER BY loan_count DESC LIMIT 1"
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.format("REPLACE(title, ' ', '') = %s"), (key,))
            row = cur.fetchone()
            if row:
                return row
            try:
                hit = next((b for b in search_books(q=title, by="title", page=1, size=10)["books"]
                            if b["title"].replace(" ", "") == key), None)
                isbn = add_to_db(hit["isbn"]) if hit else None
            except HTTPException:  # 정보나루 실패 → 일반 AI 추천으로 넘어감
                return None
            if isbn:
                cur.execute(sql.format("isbn = %s"), (isbn,))
                return cur.fetchone()
            return None
    finally:
        conn.close()


def _cosine(base, vectors):
    vectors = np.asarray(vectors, dtype=float)
    return vectors @ base / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(base) + 1e-9)


def similar_books(base, top_k):
    """(추천 목록, 같은 작가의 책). 각 책에 match: ['줄거리', '장르', '함께 대출'] 처럼 이유를 붙인다."""
    vec = np.asarray(book_collection.get(ids=[base["isbn"]], include=["embeddings"])["embeddings"][0], dtype=float)
    res = book_collection.query(query_embeddings=[vec.tolist()], n_results=CANDIDATES + 1)
    sims = {i: 1 - d for i, d in zip(res["ids"][0], res["distances"][0])}  # cosine 거리 → 유사도

    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT related_isbn FROM book_relation WHERE isbn = %s", (base["isbn"],))
            related = {r["related_isbn"] for r in cur.fetchall()}
            extra = [i for i in related if i not in sims]  # 벡터 상위 후보 밖이어도 함께 대출된 책은 후보로
            if extra:
                got = book_collection.get(ids=extra, include=["embeddings"])
                if got["ids"]:
                    sims.update(zip(got["ids"], _cosine(vec, got["embeddings"]).tolist()))
            ids = list(sims) + [base["isbn"]]
            cur.execute(f"SELECT {CARD_COLUMNS}, genre_id FROM book WHERE isbn IN %s", (ids,))
            rows = {r["isbn"]: r for r in cur.fetchall()}
            cur.execute("SELECT isbn, genre_id FROM book_subgenre WHERE isbn IN %s", (ids,))
            subs = {}
            for r in cur.fetchall():
                subs.setdefault(r["isbn"], set()).add(r["genre_id"])
            cur.execute(f"SELECT {CARD_COLUMNS} FROM book WHERE author = %s AND isbn != %s ORDER BY loan_count DESC LIMIT 10",
                        (base["author"], base["isbn"]))
            same_author = cur.fetchall()
    finally:
        conn.close()

    base_work, base_subs = work_key(base["title"], base["author"]), subs.get(base["isbn"], set())
    base_key = base["title"].replace(" ", "")
    scored, series = [], []
    for isbn, sim in sims.items():
        b = rows.get(isbn)
        if not b or isbn == base["isbn"] or work_key(b["title"], b["author"]) == base_work or b["author"] == base["author"]:
            continue
        # ponytail: 제목이 기준 책 제목으로 시작하면 시리즈로 봄 ('해리포터' → '해리포터와 마법사의 돌'). 저자 표기가 달라도 잡힘
        if b["title"].replace(" ", "").startswith(base_key):
            series.append({k: v for k, v in b.items() if k != "genre_id"})
            continue
        same_genre = bool(subs.get(isbn, set()) & base_subs) if base_subs else (base["genre_id"] is not None and b["genre_id"] == base["genre_id"])
        match = ["줄거리"] + (["장르"] if same_genre else []) + (["함께 대출"] if isbn in related else [])
        score = sim + GENRE_BONUS * same_genre + RELATION_BONUS * (isbn in related)
        scored.append((score, {**{k: v for k, v in b.items() if k != "genre_id"}, "match": match}))
    scored.sort(key=lambda x: -x[0])
    picked, per_author = [], {}
    for _, b in scored:
        if len(picked) == top_k:
            break
        if per_author.get(b["author"], 0) < MAX_PER_AUTHOR:
            per_author[b["author"]] = per_author.get(b["author"], 0) + 1
            picked.append(b)
    others = series + [b for b in same_author if work_key(b["title"], b["author"]) != base_work]
    return picked, others[:5]
