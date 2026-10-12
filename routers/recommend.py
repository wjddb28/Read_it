import httpx
from fastapi import APIRouter, HTTPException
from google.genai import errors
from pydantic import BaseModel

from ai import LLM_CONFIG, LLM_MODELS, book_collection, embed_model, llm_client
from common import get_mysql_connection

router = APIRouter(prefix="/api", tags=["recommend"])


class RecommendRequest(BaseModel):
    query: str
    top_k: int = 3
    with_comment: bool = True  # False면 Gemini를 부르지 않아 빠르게 책 목록만 돌려준다


@router.post("/recommend")
def recommend_books(request: RecommendRequest):
    try:
        # Step 1: 사용자 질문 임베딩 및 ChromaDB 검색
        query_vector = embed_model.encode(request.query).tolist()
        chroma_results = book_collection.query(
            query_embeddings=[query_vector],
            n_results=request.top_k
        )

        isbn_list = chroma_results['ids'][0]
        if not isbn_list:
            return {"message": "관련 도서를 찾을 수 없습니다.", "data": []}

        # Step 2: 검색된 ISBN으로 MySQL에서 상세 정보 조회
        conn = get_mysql_connection()
        with conn.cursor() as cursor:
            format_strings = ','.join(['%s'] * len(isbn_list))
            sql = f"SELECT isbn, title, author, description FROM book WHERE isbn IN ({format_strings})"
            cursor.execute(sql, tuple(isbn_list))
            book_details = cursor.fetchall()
        conn.close()
        book_details.sort(key=lambda b: isbn_list.index(b['isbn']))  # 유사도 순서 유지

        # Step 3: Gemini API로 추천 사유 생성 (RAG)
        prompt_context = "\n".join([f"- {b['title']} (저자: {b['author']}): {b['description'][:100]}..." for b in book_details])
        prompt = f"""
        사용자 질문: {request.query}
        검색된 도서 목록:
        {prompt_context}

        위 도서 정보를 바탕으로 사용자에게 각 책을 추천하는 다정한 코멘트를 300자 이내로 작성해줘.
        """
        # Gemini가 실패해도 검색된 책 목록은 그대로 돌려준다
        ai_comment = None
        for model in LLM_MODELS if request.with_comment else []:
            try:
                ai_comment = llm_client.models.generate_content(
                    model=model, contents=prompt, config=LLM_CONFIG).text
                break
            except (errors.APIError, httpx.HTTPError) as e:  # 과부하·시간 초과면 다음 모델로
                print(f"Gemini 호출 실패 ({model}): {e}")

        # Step 4: 최종 응답 반환
        return {
            "query": request.query,
            "ai_comment": ai_comment,
            "books": book_details
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
