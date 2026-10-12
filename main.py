import sys
from pathlib import Path

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ponytail: scripts/ 를 import 경로에 추가해 공통 코드(common, book_store 등)를 재사용.
# 코드가 커져서 패키지 구조로 정리할 때 제거
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from routers import books, recommend, search  # noqa: E402

app = FastAPI(title="Read-it API", description="AI 기반 도서 추천 서버")
# React 개발 서버(Vite 5173, CRA 3000)에서 API를 부를 수 있게 허용. 다른 주소는 .env 의 FRONTEND_ORIGINS 에 쉼표로
app.add_middleware(
    CORSMiddleware,
    allow_origins=(os.environ.get("FRONTEND_ORIGINS") or "http://localhost:5173,http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(books.router)
app.include_router(recommend.router)
app.include_router(search.router)
