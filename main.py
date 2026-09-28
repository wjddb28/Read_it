import sys
from pathlib import Path

from fastapi import FastAPI

# ponytail: scripts/ 를 import 경로에 추가해 공통 코드(common, book_store 등)를 재사용.
# 코드가 커져서 패키지 구조로 정리할 때 제거
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from routers import books, recommend  # noqa: E402

app = FastAPI(title="Read-it API", description="AI 기반 도서 추천 서버")
app.include_router(books.router)
app.include_router(recommend.router)
