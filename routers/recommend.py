import httpx
from fastapi import APIRouter, HTTPException
from google.genai import errors
from pydantic import BaseModel

from ai import LLM_CONFIG, LLM_MODELS, book_collection, embed_model, llm_client
from common import get_mysql_connection
from routers.books import CARD_COLUMNS
from routers.conditions import parse_conditions

router = APIRouter(prefix="/api", tags=["recommend"])
CONDITION_CANDIDATES = 60  # 장르 조건이 있으면 이만큼 뽑아 거른 뒤 top_k 를 고른다
INCLUDE_BONUS = 0.10       # ponytail: 감으로 정한 값. 평가셋 dev 질문으로 조정


class RecommendRequest(BaseModel):
    query: str
    top_k: int = 3
    with_comment: bool = True  # False면 Gemini를 부르지 않아 빠르게 책 목록만 돌려준다


@router.post("/recommend")
def recommend_endpoint(request: RecommendRequest):
    return recommend_books(request)


def recommend_books(request: RecommendRequest, personalize=None):
    """personalize(점수, 질문의 포함 장르): 로그인 사용자의 자연어 검색이면 후보를 서재 기록으로 다시 정렬한다."""
    try:
        # Step 1: 사용자 질문 임베딩 및 ChromaDB 검색 ('로맨스 없는' 같은 제외 조건은 떼고 검색한 뒤 거른다)
        text, include, exclude = parse_conditions(request.query)
        query_vector = embed_model.encode(text or request.query).tolist()
        chroma_results = book_collection.query(
            query_embeddings=[query_vector],
            n_results=max(CONDITION_CANDIDATES, request.top_k) if include or exclude or personalize else request.top_k
        )

        isbn_list = chroma_results['ids'][0]
        if include or exclude or personalize:
            scores = apply_conditions(isbn_list, chroma_results['distances'][0], include, exclude)
            if personalize:
                scores = personalize(scores, include)
            isbn_list = list(scores)[:request.top_k]
        if not isbn_list:
            return {"query": request.query, "message": "관련 도서를 찾을 수 없습니다.", "ai_comment": None, "books": []}

        # Step 2: 검색된 ISBN으로 MySQL에서 상세 정보 조회
        conn = get_mysql_connection()
        with conn.cursor() as cursor:
            format_strings = ','.join(['%s'] * len(isbn_list))
            sql = f"SELECT {CARD_COLUMNS} FROM book WHERE isbn IN ({format_strings})"
            cursor.execute(sql, tuple(isbn_list))
            book_details = cursor.fetchall()
        conn.close()
        book_details.sort(key=lambda b: isbn_list.index(b['isbn']))  # 유사도 순서 유지

        # Step 3: Gemini API로 추천 사유 생성 (RAG)
        ai_comment = make_comment(request.query, book_details) if request.with_comment else None

        # Step 4: 최종 응답 반환
        return {
            "query": request.query,
            "ai_comment": ai_comment,
            "books": book_details
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def apply_conditions(isbns, distances, include, exclude):
    """제외 장르가 붙은 책은 빼고, 포함 장르가 붙은 책은 가산점을 줘서 점수순으로 정렬한 {ISBN: 점수}"""
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT bs.isbn, g.name FROM book_subgenre bs JOIN genre g ON g.genre_id = bs.genre_id
                           WHERE bs.isbn IN %s""", (isbns,))
            tags = {}
            for r in cur.fetchall():
                tags.setdefault(r["isbn"], set()).add(r["name"])
    finally:
        conn.close()
    scored = {i: 1 - d + INCLUDE_BONUS * bool(tags.get(i, set()) & include)
              for i, d in zip(isbns, distances) if not tags.get(i, set()) & exclude}
    return dict(sorted(scored.items(), key=lambda x: -x[1]))


def make_comment(query, books):
    """검색된 책의 실제 정보만 근거로 추천 코멘트. Gemini가 실패하면 None (책 목록은 그대로 돌려준다)."""
    prompt_context = "\n".join([f"- {b['title']} (저자: {b['author']}): {(b['description'] or '')[:100]}..." for b in books])
    prompt = f"""
    사용자 질문: {query}
    검색된 도서 목록:
    {prompt_context}

    위 도서 정보를 바탕으로 사용자에게 각 책을 추천하는 다정한 코멘트를 300자 이내로 작성해줘.
    """
    for model in LLM_MODELS:
        try:
            return llm_client.models.generate_content(model=model, contents=prompt, config=LLM_CONFIG).text
        except (errors.APIError, httpx.HTTPError) as e:  # 과부하·시간 초과면 다음 모델로
            print(f"Gemini 호출 실패 ({model}): {e}")
    return None
