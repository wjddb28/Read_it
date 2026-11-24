"""사용자 맞춤 추천: 서재 기록(별점·코멘트·자주 읽은 작가)과 선호/비선호 장르로 고른다.
- 취향 벡터: 서재 책 줄거리 벡터의 가중합. 별점 높은 책은 +, 낮은 책은 − (가까운 책은 덜 나오게). 코멘트도 같은 부호로 섞는다
- 자주 읽은 작가(좋게 읽은 책 2권 이상)의 다른 책은 후보에 넣고 가산점, 낮게만 준 작가는 뺀다
- 선호 장르는 가산점, 비선호 장르는 뺀다. 서재 기록이 없으면 선호 장르의 인기 도서로 시작
API는 GET /api/community/recommendations (routers/community.py 가 프로필의 선호/비선호 장르를 읽어 넘긴다)
자연어 검색은 rerank_for_search 로 질문 결과에 같은 정보를 작은 가산점으로만 반영한다
"""
import logging

import numpy as np

from ai import book_collection, embed_model
from common import get_mysql_connection
from routers.books import CARD_COLUMNS, work_key
from routers.library import db_user_id
from routers.profile import fetch_genre_preferences

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
        conn = get_mysql_connection()
        try:
            with conn.cursor() as cur:
                user_id = db_user_id(cur, user)
                preferences = fetch_genre_preferences(cur, user_id)
                liked, disliked = canonical_genres(
                    preferences["likedGenres"], preferences["dislikedGenres"]
                )
                history = load_history(cur, user_id)
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


HIGH_RATING = 4     # 이 점수 이상이면 '높게 평가한 책'
PLOT_MIN = 0.65     # 측정(2026-11-16, 5,004권): 무작위 두 책은 0.6%만 넘고, 한 권당 평균 30권이 이 안에 든다
GENRE_MATCH = 0.4   # 줄거리는 멀어도 세부 장르가 같을 때. 같은 세부 장르끼리도 유사도 중앙값이 0.47이라 줄거리보다 약하게
DISAGREE = 0.5      # 같은 책을 한 명은 높게(4~5), 한 명은 낮게(1~2) 평가하면 뺀다


def genre_tags(cur, isbns):
    """isbn → 세부 장르. 세부 장르가 없는 책(비문학)은 KDC 장르. '소설' 같은 넓은 KDC 장르로 모든 소설이 같아지지 않게"""
    cur.execute("""SELECT bs.isbn, g.name FROM book_subgenre bs JOIN genre g ON g.genre_id = bs.genre_id
                   WHERE bs.isbn IN %s""", (isbns,))
    tags = {}
    for r in cur.fetchall():
        tags.setdefault(r["isbn"], set()).add(r["name"])
    cur.execute("SELECT b.isbn, g.name FROM book b JOIN genre g ON g.genre_id = b.genre_id WHERE b.isbn IN %s", (isbns,))
    for r in cur.fetchall():
        tags.setdefault(r["isbn"], {r["name"]})
    return tags


def similar_readers(user_id):
    """내가 높게 평가한 책과 같은 책, 줄거리가 비슷한 책, 같은 장르의 책을 높게 평가한 독자.
    {독자 user_id: {score, sharedBooks, sharedGenres, reason}}. 내가 높게 평가한 책이 없으면 빈 dict"""
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT v.user_id, v.isbn, v.rating, b.title, b.author
                           FROM book_review v JOIN book b ON b.isbn = v.isbn JOIN users u ON u.user_id = v.user_id
                           WHERE v.rating > 0 AND (v.user_id = %s OR u.onboarded = 1)""", (user_id,))
            reviews = cur.fetchall()
            mine = [r for r in reviews if r["user_id"] == user_id]
            liked = [r for r in mine if r["rating"] >= HIGH_RATING]
            if not liked:
                return {}
            tags = genre_tags(cur, tuple({r["isbn"] for r in reviews}))
    finally:
        conn.close()

    my_rating = {work_key(r["title"], r["author"]): r["rating"] for r in mine}
    others = {}
    for r in reviews:
        if r["user_id"] != user_id:
            others.setdefault(r["user_id"], []).append(r)
    ids = list({r["isbn"] for r in liked} | {r["isbn"] for rs in others.values() for r in rs if r["rating"] >= HIGH_RATING})
    got = book_collection.get(ids=ids, include=["embeddings"])
    vecs = {i: unit(e) for i, e in zip(got["ids"], got["embeddings"])}

    def match(a, b):
        """(점수, 종류, 같은 장르): 내가 좋아한 책 a 와 그 독자가 높게 평가한 책 b"""
        shared = tags.get(a["isbn"], set()) & tags.get(b["isbn"], set())
        if work_key(a["title"], a["author"]) == work_key(b["title"], b["author"]):
            return 1.0, "same", shared
        cos = float(vecs[a["isbn"]] @ vecs[b["isbn"]]) if a["isbn"] in vecs and b["isbn"] in vecs else 0.0
        if cos >= PLOT_MIN:
            return cos, "plot", shared
        return (GENRE_MATCH, "genre", shared) if shared else (0.0, None, shared)

    readers = {}
    for other, rs in others.items():
        high = [r for r in rs if r["rating"] >= HIGH_RATING]
        total, same, genres, best = 0.0, 0, set(), None
        for b in rs:
            mine_r = my_rating.get(work_key(b["title"], b["author"]))
            if mine_r and (mine_r <= 2 < HIGH_RATING <= b["rating"] or b["rating"] <= 2 < HIGH_RATING <= mine_r):
                total -= DISAGREE
        for b in high:
            m, kind, shared, a = max(((*match(a, b), a) for a in liked), key=lambda x: x[0] * RATING_WEIGHT[x[3]["rating"]])
            if not kind:
                continue
            gain = m * RATING_WEIGHT[a["rating"]] * RATING_WEIGHT[b["rating"]]
            total += gain
            same += kind == "same"
            genres |= shared
            if not best or gain > best[0]:
                best = (gain, kind, a, b)
        score = total / np.sqrt(len(high)) if high else total  # 별점을 많이 남긴 독자가 개수만으로 앞서지 않게
        if best and score > 0:
            _, kind, a, b = best
            reason = (f"둘 다 「{a['title']}」에 높은 별점" if kind == "same" else
                      f"「{b['title']}」에 {b['rating']}점 · 내가 좋아한 「{a['title']}」{with_josa(a['title'])} "
                      + ("줄거리가 비슷해요" if kind == "plot" else "같은 장르예요"))
            readers[other] = {"score": round(float(score), 3), "sharedBooks": same,
                              "sharedGenres": sorted(genres), "reason": reason}
    return readers


def genre_candidates(cur, target_genres, user_id, limit):
    if not target_genres:
        return []
    cur.execute(f"""SELECT {CARD_COLUMNS} FROM book
                    JOIN (
                        SELECT isbn AS matched_isbn, COUNT(DISTINCT genre_id) AS overlap
                        FROM (
                            SELECT isbn, genre_id FROM book WHERE genre_id IS NOT NULL
                            UNION ALL SELECT isbn, genre_id FROM book_subgenre
                        ) tags JOIN genre USING (genre_id)
                        WHERE genre.name IN %s
                        GROUP BY isbn
                    ) matches ON matches.matched_isbn = book.isbn
                    WHERE NOT EXISTS (
                        SELECT 1 FROM reading_record r WHERE r.user_id = %s AND r.isbn = book.isbn
                    )
                    ORDER BY matches.overlap DESC, loan_count DESC, isbn LIMIT %s""",
                (tuple(sorted(target_genres)), user_id, limit))
    return cur.fetchall()


def personal_books(user_id, liked=(), disliked=(), top_k=6):
    """Rank by genre overlap first, then by similarity to books in the user's library."""
    liked, disliked = canonical_genres(liked, disliked)
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            history = load_history(cur, user_id)
            shelf = [h for h in history if h["status"] is not None]
            shelf_ids = tuple(h["isbn"] for h in shelf)
            shelf_tags = book_tags(cur, shelf_ids) if shelf_ids else {}
            shelf_genres = set().union(*shelf_tags.values()) - disliked
            target_genres = liked | shelf_genres
            read = {work_key(h["title"], h["author"]) for h in history}

            if not target_genres and not shelf:
                return []
            rows = {b["isbn"]: b for b in genre_candidates(cur, target_genres, user_id, CANDIDATES * 3)}
            taste, read_vecs, good, fav_authors, bad_authors = reading_signals(shelf)
            if fav_authors:
                cur.execute(f"""SELECT {CARD_COLUMNS} FROM book WHERE author IN %s
                               ORDER BY loan_count DESC, isbn LIMIT %s""",
                            (tuple(sorted(fav_authors)), CANDIDATES))
                rows.update((b["isbn"], b) for b in cur.fetchall())
            sims = {}
            cand_vecs = {}
            if taste is not None:
                res = book_collection.query(query_embeddings=[taste.tolist()], n_results=CANDIDATES)
                sims = {i: 1 - d for i, d in zip(res["ids"][0], res["distances"][0])}
                extra = tuple(i for i in sims if i not in rows)
                if extra:
                    cur.execute(f"SELECT {CARD_COLUMNS} FROM book WHERE isbn IN %s", (extra,))
                    rows.update((b["isbn"], b) for b in cur.fetchall())
                if rows:
                    got = book_collection.get(ids=list(rows), include=["embeddings"])
                    cand_vecs = {i: unit(e) for i, e in zip(got["ids"], got["embeddings"])}

            # Fill with eligible popular books if the user has few genre or vector matches.
            cur.execute(f"""SELECT {CARD_COLUMNS} FROM book
                            WHERE NOT EXISTS (
                                SELECT 1 FROM reading_record r WHERE r.user_id = %s AND r.isbn = book.isbn
                            )
                            ORDER BY loan_count DESC, isbn LIMIT %s""", (user_id, CANDIDATES * 3))
            for b in cur.fetchall():
                rows.setdefault(b["isbn"], b)
            tags = book_tags(cur, tuple(rows)) if rows else {}
    finally:
        conn.close()

    good_vecs = [(h["title"], read_vecs[h["isbn"]]) for h in good if h["isbn"] in read_vecs]
    scored = []
    for isbn, b in rows.items():
        t = tags.get(isbn, set())
        work = work_key(b["title"], b["author"])
        if work in read or b["author"] in bad_authors or t & disliked:
            continue
        preferred = t & liked
        shared = t & shelf_genres
        overlap = len(preferred | shared)
        reasons = []
        if preferred:
            reasons.append("선호 장르 " + ", ".join(sorted(preferred)))
        if shared:
            reasons.append("서재와 겹치는 장르 " + ", ".join(sorted(shared)))
        if b["author"] in fav_authors:
            reasons.append(f"자주 읽은 작가 {b['author']}")
        shelf_title = None
        sim = sims.get(isbn, 0.0)
        if isbn in cand_vecs:
            sim = float(cand_vecs[isbn] @ taste)
            if good_vecs:
                shelf_title, _ = max(good_vecs, key=lambda x: float(x[1] @ cand_vecs[isbn]))
                reasons.append(f"「{shelf_title}」{with_josa(shelf_title)} 비슷해요")
        if shelf_title is None and shared:
            closest = max(shelf, key=lambda item: len(shared & shelf_tags.get(item["isbn"], set())))
            shelf_title = closest["title"]
        similarity = sim + AUTHOR_BONUS * (b["author"] in fav_authors)
        rank = (overlap, len(preferred) + len(shared), similarity, b["loan_count"] or 0)
        scored.append((rank, work, {
            **b, "reasons": reasons,
            "matchedPreferredGenres": sorted(preferred),
            "similarShelfTitle": shelf_title,
        }))

    scored.sort(key=lambda item: item[0], reverse=True)
    picked, deferred, seen, author_counts = [], [], set(), {}
    for _, work, book in scored:
        if work in seen:
            continue
        seen.add(work)
        author = book["author"]
        count = author_counts.get(author, 0)
        if count >= MAX_PER_AUTHOR:
            deferred.append(book)
            continue
        picked.append(book)
        author_counts[author] = count + 1
        if len(picked) >= top_k:
            break
    return (picked + deferred)[:top_k]


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
