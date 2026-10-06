"""여러 라우터가 같이 쓰는 AI 자원 (서버 시작 시 한 번만 로딩)."""
import os

import chromadb
from google import genai
from google.genai import types
from sentence_transformers import SentenceTransformer

from common import CHROMA_DIR  # .env 로딩 포함

print("모델 및 DB 로딩 중...")
embed_model = SentenceTransformer('jhgan/ko-sbert-multitask')
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
book_collection = chroma_client.get_collection(name="books")  # 없으면 scripts/load_seed.py 먼저 실행

# Gemini API 키는 .env 의 GEMINI_API_KEY 에서 읽음.
# 같은 모델로 재시도하지 않고 실패하면 다음 모델로 넘긴다 (모델 선택 근거: docs/LLM_응답시간_측정.md)
llm_client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(timeout=15_000, retry_options=types.HttpRetryOptions(attempts=1)),
)
LLM_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
LLM_CONFIG = types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
