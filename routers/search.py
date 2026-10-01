"""검색창 하나로 받는 검색. ai=false면 일반 검색(제목·저자·ISBN, 정보나루 실시간),
ai=true면 문장으로 찾는 AI 추천 검색."""
import re
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Query

from ai import embed_model
from common import get_mysql_connection
from routers.books import search_books
from routers.recommend import RecommendRequest, recommend_books

router = APIRouter(prefix="/api", tags=["search"])

ISBN_RE = re.compile(r"^(97[89])?\d{9}[\dXx]$")
HANGUL_OR_LATIN = re.compile(r"[가-힣A-Za-z]")
# AI 검색에서 추천 요청으로 보기 어려운 입력 예시. 질문이 이 중 하나와 매우 비슷하면 다시 입력을 요청한다.
# 가나다라·123·안녕은 실제 같은 제목의 책이 있지만, 일반 검색에서는 이 검사를 하지 않으므로 그대로 찾을 수 있다.
# 맥락을 알 수 없는 입력(자판 연타·인사·테스트 등)만 넣는다. '심심해'·'뭐하지'·'아무거나'처럼 조금이라도 바람이 있으면 AI 추천으로 보낸다
NONSENSE_EXAMPLES = ["몰라", "모르겠어", "asdf", "qwer", "zxcv",
                     "ㅁㄴㅇㄹ", "ㅋㅋㅋ", "ㅎㅎㅎ", "가나다라", "테스트", "test", "123", "안녕", "안녕하세요", "하이",
                     "hello"]
NONSENSE_THRESHOLD = 0.80  # 측정값: 엉뚱한 입력 0.84~0.96, 정상 질문 최고 0.61
_nonsense_vecs = None

NOT_FOUND_MESSAGE = "검색 결과가 없어요. 제대로 입력했는지 확인해주세요. 원하는 책을 찾으러 AI 검색으로 가볼까요?"
RETRY_MESSAGE = "'비 오는 날 읽기 좋은 책 추천해줘'처럼 검색해주시면 더 다양한 책을 추천해드릴게요."


def random_books(n=5):
    """맥락을 모르는 검색어일 때 대신 보여줄 우리 DB의 책.
    ponytail: 지금은 전체에서 무작위. 서재 기록이 쌓이면 사용자들이 읽은 책 중에서 고르도록 바꾼다"""
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT isbn, title, author, description, cover_image_url FROM book ORDER BY RAND() LIMIT %s", (n,))
            return cur.fetchall()
    finally:
        conn.close()


def is_nonsense(q):
    """AI 검색용: 자음·모음·숫자·기호만, 같은 글자 반복, 엉뚱한 입력 예시와 비슷하면 True"""
    global _nonsense_vecs
    compact = q.replace(" ", "")
    if (len(compact) < 2 or not HANGUL_OR_LATIN.search(compact)
            or len(set(compact)) == 1 or (len(compact) >= 4 and len(set(compact)) <= 2)):
        return True
    if _nonsense_vecs is None:
        _nonsense_vecs = embed_model.encode(NONSENSE_EXAMPLES, normalize_embeddings=True)
    return float((_nonsense_vecs @ embed_model.encode(q, normalize_embeddings=True)).max()) >= NONSENSE_THRESHOLD


def general_search(q):
    """사용자가 아는 책을 찾는 검색이라 속도 우선: 모델 호출 없이 정보나루만 쓴다."""
    compact = q.replace(" ", "").replace("-", "")
    if ISBN_RE.match(compact):
        return search_books(q=compact, by="isbn", page=1, size=20)["books"]
    # 제목·저자 검색을 동시에 보내고 합친다 (제목 결과 우선, 같은 ISBN은 한 번만)
    with ThreadPoolExecutor(2) as ex:
        by_title, by_author = ex.map(lambda by: search_books(q=q, by=by, page=1, size=20), ("title", "author"))
    books, seen = [], set()
    for b in by_title["books"] + by_author["books"]:
        if b["isbn"] not in seen:
            seen.add(b["isbn"])
            books.append(b)
    return books


@router.get("/search")
def smart_search(q: str = Query(min_length=1, description="제목, 저자, ISBN 또는 (AI 검색일 때) 문장"),
                 ai: bool = Query(False, description="true면 AI 추천 검색"),
                 top_k: int = Query(5, ge=1, le=20, description="AI 검색 결과 수"),
                 comment: bool = Query(False, description="AI 검색일 때 추천 코멘트 생성 (느림)")):
    q = q.strip()
    if not ai:
        books = general_search(q)
        if not books:
            return {"mode": "general", "query": q, "books": [], "message": NOT_FOUND_MESSAGE, "suggest_ai": True}
        return {"mode": "general", "query": q, "books": books}

    if is_nonsense(q):
        return {"mode": "retry", "query": q, "books": random_books(), "message": RETRY_MESSAGE}
    res = recommend_books(RecommendRequest(query=q, top_k=top_k, with_comment=comment))
    return {"mode": "ai", "query": q, "ai_comment": res.get("ai_comment"), "books": res.get("books", [])}
