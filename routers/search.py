"""검색창 하나로 받는 통합 검색 (명세서 3.1 스마트 도서 검색 라우팅).
키워드면 정보나루 실시간 검색, 문장이면 AI 추천으로 보낸다."""
import re
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Query

from ai import embed_model
from routers.books import search_books
from routers.recommend import RecommendRequest, recommend_books

router = APIRouter(prefix="/api", tags=["search"])

ISBN_RE = re.compile(r"^(97[89])?\d{9}[\dXx]$")
# ponytail: 단어 규칙으로 문장형 질문을 판별. 오분류가 많으면 Gemini 분류로 교체
NL_HINTS = ("추천", "읽기 좋은", "읽고 싶", "같은", "비슷한", "느낌", "분위기", "?",
            "한 책", "는 책", "은 책", "할 책", "만한")


HANGUL_OR_LATIN = re.compile(r"[가-힣A-Za-z]")
# 검색어로 보기 어려운 입력 예시. 질문이 이 중 하나와 매우 비슷하면 다시 입력을 요청한다
NONSENSE_EXAMPLES = ["아무거나", "몰라", "모르겠어", "아무 책", "암거나", "asdf", "qwer", "zxcv",
                     "ㅁㄴㅇㄹ", "ㅋㅋㅋ", "ㅎㅎㅎ", "가나다라", "테스트", "test", "123", "안녕", "하이",
                     "hello", "심심해", "뭐하지"]
NONSENSE_THRESHOLD = 0.80  # 측정값: 엉뚱한 입력 0.84~0.96, 정상 질문 최고 0.61
_nonsense_vecs = None


def classify_query(q):
    """'retry' | 'isbn' | 'ai' | 'keyword' (API·모델 호출 없이 규칙만으로)"""
    s = q.strip()
    compact = s.replace(" ", "")
    if ISBN_RE.match(compact.replace("-", "")):
        return "isbn"
    if (len(compact) < 2 or not HANGUL_OR_LATIN.search(compact)  # 자음·모음·숫자·기호만
            or len(set(compact)) == 1 or (len(compact) >= 4 and len(set(compact)) <= 2)):  # 같은 글자 반복
        return "retry"
    if any(h in s for h in NL_HINTS):
        return "ai"
    return "keyword"


@router.get("/search")
def smart_search(q: str = Query(min_length=1, description="키워드, ISBN 또는 문장"),
                 top_k: int = Query(5, ge=1, le=20, description="AI 추천일 때 결과 수"),
                 comment: bool = Query(False, description="AI 추천일 때 추천 코멘트 생성 (느림)")):
    global _nonsense_vecs
    mode = classify_query(q)
    if mode != "retry" and mode != "isbn":
        if _nonsense_vecs is None:
            _nonsense_vecs = embed_model.encode(NONSENSE_EXAMPLES, normalize_embeddings=True)
        if float((_nonsense_vecs @ embed_model.encode(q, normalize_embeddings=True)).max()) >= NONSENSE_THRESHOLD:
            mode = "retry"
    if mode == "retry":
        return {"mode": "retry", "query": q, "message": "검색어를 이해하지 못했어요. 책 제목, 저자 또는 찾는 책을 문장으로 입력해 주세요.", "books": []}

    if mode == "isbn":
        res = search_books(q=q.replace("-", "").strip(), by="isbn", page=1, size=20)
        return {"mode": "isbn", "query": q, "books": res["books"]}

    if mode == "keyword":
        # 제목·저자 검색을 동시에 보내고 합친다 (제목 결과 우선, 같은 ISBN은 한 번만)
        with ThreadPoolExecutor(2) as ex:
            by_title, by_author = ex.map(
                lambda by: search_books(q=q, by=by, page=1, size=20), ("title", "author"))
        books, seen = [], set()
        for b in by_title["books"] + by_author["books"]:
            if b["isbn"] not in seen:
                seen.add(b["isbn"])
                books.append(b)
        if books:
            return {"mode": "keyword", "query": q, "books": books}
        # 키워드로 아무것도 안 나오면 문장형 질문으로 보고 AI 추천

    res = recommend_books(RecommendRequest(query=q, top_k=top_k, with_comment=comment))
    return {"mode": "ai", "query": q, "ai_comment": res.get("ai_comment"), "books": res.get("books", [])}
