import sys
import logging
import os
import re
from importlib import import_module
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

# ponytail: scripts/ 를 import 경로에 추가해 공통 코드(common, book_store 등)를 재사용.
# 코드가 커져서 패키지 구조로 정리할 때 제거
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from routers import books, recommend, auth, catalog, library  # noqa: E402

app = FastAPI(title="Read-it API", description="AI 기반 도서 추천 서버")
app.include_router(books.router)
app.include_router(recommend.router)

app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(library.router)


@app.get("/api/search", tags=["search"])
def search_endpoint(
    q: str = Query(min_length=1, description="제목, 저자, ISBN 또는 AI 검색 문장"),
    ai: bool = Query(False, description="true면 AI 추천 검색"),
    top_k: int = Query(5, ge=1, le=20),
    comment: bool = Query(False),
):
    """기존 검색 함수를 호출하되 AI 초기화가 서버 시작을 막지 않게 한다."""
    try:
        search_module = import_module("routers.search")
    except (Exception, SystemExit) as exc:
        logging.getLogger("uvicorn.error").warning(
            "Search module initialization failed: %s", type(exc).__name__,
        )
        raise HTTPException(
            503,
            "AI 검색을 준비하지 못했어요. 담당자에게 ChromaDB 경로와 books 컬렉션, AI 설정을 확인해달라고 요청해주세요.",
        ) from exc
    result = search_module.smart_search(q=q, ai=ai, top_k=top_k, comment=False if ai else comment)
    if ai and comment and result.get("mode") == "ai":
        from routers.recommendation_view import align_recommendations
        return align_recommendations(q, result)
    return result


@app.exception_handler(StarletteHTTPException)
async def report_api_error(request: Request, exc: StarletteHTTPException):
    """검색 구현은 유지하고, 외부 API 실패 원인만 서버 로그로 남긴다."""
    if request.url.path.startswith("/api/books/") and exc.status_code >= 500:
        cause = exc.__cause__ or exc.__context__
        if cause is not None:
            reason = str(cause)
            # requests 예외에는 API 키가 포함된 URL이 들어갈 수 있다.
            for name in ("LIBRARY_API_KEY", "GEMINI_API_KEY", "MYSQL_PASSWORD"):
                value = os.environ.get(name)
                if value:
                    reason = reason.replace(value, "[REDACTED]")
            reason = re.sub(r"https?://\S+", "[URL REDACTED]", reason)
            reason = re.sub(r"(?i)(authKey\s*[=:]\s*)[^\s&,]+", r"\1[REDACTED]", reason)
            reason = reason.replace("\r", " ").replace("\n", " ")[:1000]
            logging.getLogger("uvicorn.error").warning(
                "%s failed (%s): %s: %s",
                request.url.path, exc.status_code, type(cause).__name__, reason,
            )
    return await http_exception_handler(request, exc)
