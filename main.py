from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import chromadb
from sentence_transformers import SentenceTransformer
from google import genai
import os

from scripts.common import CHROMA_DIR, get_mysql_connection  # .env 로딩 포함

# 1. FastAPI 앱 초기화
app = FastAPI(title="Read-it API", description="AI 기반 도서 추천 서버")

# 2. AI 모델 및 외부 API 초기화
print("모델 및 DB 로딩 중...")
embed_model = SentenceTransformer('jhgan/ko-sbert-multitask')
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
book_collection = chroma_client.get_collection(name="books")  # 없으면 scripts/load_seed.py 먼저 실행

# Gemini API 키는 .env 의 GEMINI_API_KEY 에서 읽음
llm_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
LLM_MODEL = "gemini-3.7-flash"

# 3. 데이터 모델 정의 (요청/응답 포맷)
class RecommendRequest(BaseModel):
    query: str
    top_k: int = 3

@app.post("/api/recommend")
async def recommend_books(request: RecommendRequest):
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

        # Step 3: Gemini API로 추천 사유 생성 (RAG)
        prompt_context = "\n".join([f"- {b['title']} (저자: {b['author']}): {b['description'][:100]}..." for b in book_details])
        prompt = f"""
        사용자 질문: {request.query}
        검색된 도서 목록:
        {prompt_context}
        
        위 도서 정보를 바탕으로 사용자에게 각 책을 추천하는 다정한 코멘트를 300자 이내로 작성해줘.
        """
        llm_response = llm_client.models.generate_content(model=LLM_MODEL, contents=prompt)

        # Step 4: 최종 응답 반환
        return {
            "query": request.query,
            "ai_comment": llm_response.text,
            "books": book_details
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))