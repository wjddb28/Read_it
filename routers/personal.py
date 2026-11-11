"""사용자 맞춤 추천: 서재 기록(별점·코멘트·자주 읽은 작가)과 선호/비선호 장르로 고른다.
- 취향 벡터: 서재 책 줄거리 벡터의 가중합. 별점 높은 책은 +, 낮은 책은 − (가까운 책은 덜 나오게). 코멘트도 같은 부호로 섞는다
- 자주 읽은 작가(좋게 읽은 책 2권 이상)의 다른 책은 후보에 넣고 가산점, 낮게만 준 작가는 뺀다
- 선호 장르는 가산점, 비선호 장르는 뺀다. 서재 기록이 없으면 선호 장르의 인기 도서로 시작
API는 GET /api/community/recommendations (routers/community.py 가 프로필의 선호/비선호 장르를 읽어 넘긴다)
자연어 검색은 rerank_for_search 로 질문 결과에 같은 정보를 작은 가산점으로만 반영한다
"""
import json
import logging

import numpy as np

from ai import book_collection, embed_model
from common import get_mysql_connection
from routers.books import CARD_COLUMNS, work_key
from routers.community_store import database, ensure_profile
from routers.library import db_user_id

# ponytail: 가중치·가산점은 감으로 정한 값. 서재 기록이 쌓이면 '나중에 높게 준 책이 추천에 있었나'로 조정
RATING_WEIGHT = {5: 1.0, 4: 0.7, 3: 0.2, 2: -0.5, 1: -1.0}
NO_RATING_WEIGHT = 0.3   # 별점 없이 담아만 둔 책도 관심 있는 책으로 본다
COMMENT_WEIGHT = 0.5     # 코멘트 벡터는 책 벡터의 절반만큼
TASTE_WEIGHT = 0.15      # 자연어 검색: 질문 유사도에 더하는 취향 유사도 비중 (질문이 우선)
AUTHOR_BONUS = 0.08
GENRE_BONUS = 0.05
MAX_PER_AUTHOR = 2
CANDIDATES = 80
# 팀원 장르 선택 화면(GenrePicker)의 이름 → DB genre 이름
GENRE_ALIASES = {"소설(일반문학)": "소설", "고전소설": "소설", "스릴러": "스릴러·호러", "공포·스릴러": "스릴러·호러",
                 "경제·경영": "경제경영", "사회·정치": "사회과학", "IT·컴퓨터": "기술과학", "과학(일반)": "자연과학",
                 "종교학": "종교"}


def unit(v):
    v = np.asarray(v, dtype=float)
    return v / (np.linalg.norm(v) + 1e-9)


def with_josa(word):
    """받침이 있으면 '과', 없으면 '와' ('가공범과', '모순과', '나미야 잡화점의 기적과')"""
    last = word.rstrip()[-1:] or "가"
    return "과" if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 else "와"


def load_history(cur, user_id):
    """서재 책과 별점·코멘트 (리뷰만 남긴 책도 포함)"""
    cur.execute("""SELECT b.isbn, b.title, b.author, r.status, v.rating, v.content
                   FROM book b
                   LEFT JOIN reading_record r ON r.isbn = b.isbn AND r.user_id = %s
                   LEFT JOIN book_review v ON v.isbn = b.isbn AND v.user_id = %s
                   WHERE r.record_id IS NOT NULL OR v.review_id IS NOT NULL""", (user_id, user_id))
    return cur.fetchall()


def weight(row):
    return RATING_WEIGHT[row["rating"]] if row["rating"] else NO_RATING_WEIGHT


def taste_vector(history):
    """(취향 벡터 또는 None, isbn→책 벡터). 좋게 읽은 책이 하나도 없으면 None"""
    got = book_collection.get(ids=[h["isbn"] for h in history], include=["embeddings"])
    vecs = {i: unit(e) for i, e in zip(got["ids"], got["embeddings"])}
    if not vecs:  # 서재 책이 벡터 DB에 하나도 없으면 취향을 계산할 수 없다
        return None, vecs
    comments = [h for h in history if (h["content"] or "").strip()]
    comment_vecs = embed_model.encode([h["content"] for h in comments], normalize_embeddings=True) if comments else []
    total = np.zeros(next(iter(vecs.values())).shape)
    for h in history:
        if h["isbn"] in vecs:
            total += weight(h) * vecs[h["isbn"]]
    for h, cv in zip(comments, comment_vecs):
        total += COMMENT_WEIGHT * weight(h) * np.asarray(cv)
    if not any(weight(h) > 0 for h in history):
        return None, vecs
    return unit(total), vecs


def book_tags(cur, isbns):
    """isbn → {KDC 장르, 세부 장르 이름}"""
    cur.execute("""SELECT b.isbn, g.name FROM book b JOIN genre g ON g.genre_id = b.genre_id WHERE b.isbn IN %s
                   UNION SELECT bs.isbn, g.name FROM book_subgenre bs JOIN genre g ON g.genre_id = bs.genre_id
                   WHERE bs.isbn IN %s""", (isbns, isbns))
    tags = {}
    for r in cur.fetchall():
        tags.setdefault(r["isbn"], set()).add(r["name"])
    return tags


def canonical_genres(liked, disliked):
    liked = {GENRE_ALIASES.get(g, g) for g in liked}
    return liked, {GENRE_ALIASES.get(g, g) for g in disliked} - liked


def reading_signals(history):
    """서재 기록 → (취향 벡터, 책 벡터, 좋게 읽은 기록, 자주 읽은 작가, 낮게만 준 작가)"""
    taste, read_vecs = taste_vector(history) if history else (None, {})
    good = [h for h in history if weight(h) > 0]
    counts = {}
    for h in good:
        counts[h["author"]] = counts.get(h["author"], 0) + 1
    fav_authors = {a for a, n in counts.items() if a and n >= 2}
    bad_authors = {h["author"] for h in history if weight(h) < 0} - set(counts)
    return taste, read_vecs, good, fav_authors, bad_authors


def finished_works(history):
    """검색에서 뺄 작품. 담아만 둔(WISH) 책은 아직 읽지 않았으므로 검색에 남긴다"""
    return {work_key(h["title"], h["author"]) for h in history if h["status"] != "WISH"}


def read_works(user):
    """로그인 사용자가 읽은 작품. 조회에 실패하면 빈 집합 (검색은 계속)"""
    try:
        conn = get_mysql_connection()
        try:
            with conn.cursor() as cur:
                return finished_works(load_history(cur, db_user_id(cur, user)))
        finally:
            conn.close()
    except Exception as exc:
        logging.getLogger("uvicorn.error").warning("Read history unavailable: %s", type(exc).__name__)
        return set()


def rerank_for_search(user, query, scores, asked):
    """자연어 검색 후보 {isbn: 점수}를 서재 기록으로 다시 정렬한다. 질문에서 직접 찾은 장르(asked)가 비선호보다 우선.
    서재 기록이 없거나 개인화에 실패하면 원래 검색 결과를 그대로 돌려준다"""
    try:
        with database() as community_db:
            profile = ensure_profile(community_db, user)
            liked, disliked = canonical_genres(json.loads(profile["liked"]), json.loads(profile["disliked"]))
        conn = get_mysql_connection()
        try:
            with conn.cursor() as cur:
                history = load_history(cur, db_user_id(cur, user))
                if not history:
                    return scores
                taste, _, _, fav_authors, bad_authors = reading_signals(history)
                ids = tuple(scores)
                cur.execute("SELECT isbn, title, author FROM book WHERE isbn IN %s", (ids,))
                rows = {r["isbn"]: r for r in cur.fetchall()}
                tags = book_tags(cur, ids)
        finally:
            conn.close()
        vecs = {}
        if taste is not None:
            got = book_collection.get(ids=list(ids), include=["embeddings"])
            vecs = {i: unit(e) for i, e in zip(got["ids"], got["embeddings"])}
        read, disliked, out = finished_works(history), disliked - asked, {}
        for isbn, score in scores.items():
            b, t = rows.get(isbn), tags.get(isbn, set())
            if not b or work_key(b["title"], b["author"]) in read or t & disliked:
                continue
            if b["author"] in bad_authors and (b["author"] or "") not in query:  # 작가를 직접 물으면 질문 우선
                continue
            if isbn in vecs:
                score += TASTE_WEIGHT * float(vecs[isbn] @ taste)
            out[isbn] = score + AUTHOR_BONUS * (b["author"] in fav_authors) + GENRE_BONUS * bool(t & liked)
        # 질문이 장르를 말했으면 그 장르의 책을 항상 앞에 둔다 (취향 점수가 질문을 이기지 않게)
        return dict(sorted(out.items(), key=lambda x: (not tags.get(x[0], set()) & asked, -x[1])))
    except Exception as exc:
        logging.getLogger("uvicorn.error").warning("Search personalization unavailable: %s", type(exc).__name__)
        return scores


def personal_books(user_id, liked=(), disliked=(), top_k=6):
    """맞춤 추천 책 목록. 각 책에 reasons: ['자주 읽은 작가 ○○', '좋아하는 장르 판타지', '「X」와 비슷해요']"""
    liked, disliked = canonical_genres(liked, disliked)
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            history = load_history(cur, user_id)
            taste, read_vecs, good, fav_authors, bad_authors = reading_signals(history)
            read = {work_key(h["title"], h["author"]) for h in history}

            if taste is None:
                return cold_start(cur, liked, disliked, read, top_k)

            res = book_collection.query(query_embeddings=[taste.tolist()], n_results=CANDIDATES)
            sims = {i: 1 - d for i, d in zip(res["ids"][0], res["distances"][0])}
            if fav_authors:  # 자주 읽은 작가의 책은 벡터 상위 밖이어도 후보로
                cur.execute(f"SELECT isbn FROM book WHERE author IN %s", (tuple(fav_authors),))
                extra = [r["isbn"] for r in cur.fetchall() if r["isbn"] not in sims]
                got = book_collection.get(ids=extra, include=["embeddings"]) if extra else {"ids": []}
                for i, e in zip(got["ids"], got.get("embeddings", [])):
                    sims[i] = float(unit(e) @ taste)
            ids = tuple(sims)
            cur.execute(f"SELECT {CARD_COLUMNS} FROM book WHERE isbn IN %s", (ids,))
            rows = {r["isbn"]: r for r in cur.fetchall()}
            tags = book_tags(cur, ids)
            got = book_collection.get(ids=list(ids), include=["embeddings"])
            cand_vecs = {i: unit(e) for i, e in zip(got["ids"], got["embeddings"])}
    finally:
        conn.close()

    good_vecs = [(h["title"], read_vecs[h["isbn"]]) for h in good if h["isbn"] in read_vecs]
    scored = []
    for isbn, sim in sims.items():
        b, t = rows.get(isbn), tags.get(isbn, set())
        if not b or work_key(b["title"], b["author"]) in read or b["author"] in bad_authors or t & disliked:
            continue
        reasons = []
        if b["author"] in fav_authors:
            reasons.append(f"자주 읽은 작가 {b['author']}")
        if t & liked:
            reasons.append("좋아하는 장르 " + ", ".join(sorted(t & liked)))
        if isbn in cand_vecs and good_vecs:
            title, _ = max(good_vecs, key=lambda x: float(x[1] @ cand_vecs[isbn]))
            reasons.append(f"「{title}」{with_josa(title)} 비슷해요")
        score = sim + AUTHOR_BONUS * (b["author"] in fav_authors) + GENRE_BONUS * bool(t & liked)
        scored.append((score, {**b, "reasons": reasons}))
    scored.sort(key=lambda x: -x[0])
    picked, per_author = [], {}
    for _, b in scored:
        if len(picked) == top_k:
            break
        if per_author.get(b["author"], 0) < MAX_PER_AUTHOR:
            per_author[b["author"]] = per_author.get(b["author"], 0) + 1
            picked.append(b)
    return picked


def cold_start(cur, liked, disliked, read, top_k):
    """서재 기록이 없을 때: 선호 장르의 인기 도서 (비선호 장르 제외). 선호 장르도 없으면 빈 목록"""
    if not liked:
        return []
    cur.execute(f"""SELECT {CARD_COLUMNS} FROM book WHERE isbn IN (
                      SELECT b.isbn FROM book b JOIN genre g ON g.genre_id = b.genre_id WHERE g.name IN %s
                      UNION SELECT bs.isbn FROM book_subgenre bs JOIN genre g ON g.genre_id = bs.genre_id WHERE g.name IN %s)
                    ORDER BY loan_count DESC LIMIT %s""", (tuple(liked), tuple(liked), top_k * 5))
    rows = cur.fetchall()
    tags = book_tags(cur, tuple(r["isbn"] for r in rows)) if rows else {}
    picked = []
    for b in rows:
        t = tags.get(b["isbn"], set())
        if not t & disliked and work_key(b["title"], b["author"]) not in read:
            picked.append({**b, "reasons": ["좋아하는 장르 " + ", ".join(sorted(t & liked))]})
        if len(picked) == top_k:
            break
    return picked


def recommendations_for(user, liked, disliked, top_k=6):
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            user_id = db_user_id(cur, user)
    finally:
        conn.close()
    books = personal_books(user_id, liked, disliked, top_k)
    message = None if books else "서재에 책을 담거나 좋아하는 장르를 고르면 맞춤 책을 추천해드려요."
    return {"books": books, "message": message}
