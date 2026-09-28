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

# Gemini API 키는 .env 의 GEMINI_API_KEY 에서 읽음. 503(과부하)·429 등은 SDK가 지수 백오프로 재시도
llm_client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=3)),
)
LLM_MODEL = "gemini-3.7-flash"
LLM_CONFIG = types.GenerateContentConfig(
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
