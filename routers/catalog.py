"""Read-only presentation adapter: exact count, global title order, ten per page.

The original search/recommendation functions and database schema are unchanged.
All provider pages are collected before sorting so page boundaries are stable.
"""
import math
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from routers.books import search_books, work_key

router = APIRouter(prefix="/api/catalog", tags=["books"])
PAGE_SIZE = 10
SOURCE_SIZE = 50
_cache = OrderedDict()
_cache_lock = threading.Lock()
_collection_lock = threading.Lock()


def title_key(book):
    return (unicodedata.normalize("NFC", book.get("title") or "").casefold(),
            book.get("author") or "", book.get("isbn") or "")


def collect(q, by):
    key = (q, by)
    # Avoid duplicate full-provider scans from concurrent browser requests.
    with _collection_lock:
        with _cache_lock:
            cached = _cache.get(key)
            if cached and cached[0] > time.monotonic():
                _cache.move_to_end(key)
                return cached[1], cached[2]
        compact = q.replace(" ", "").replace("-", "")
        fields = ["isbn"] if by == "all" and re.fullmatch(r"(?:97[89])?\d{9}[\dXx]", compact) else (
            ["title", "author", "keyword"] if by == "all" else [by])
        query = compact if fields == ["isbn"] else q
        found, corrected = [], None
        for field in fields:
            first = search_books(q=query, by=field, page=1, size=SOURCE_SIZE)
            found.extend(first["books"])
            corrected = corrected or first.get("corrected_query")
            pages = math.ceil(int(first.get("total") or 0) / SOURCE_SIZE)
            def fetch(page):
                return search_books(q=query, by=field, page=page, size=SOURCE_SIZE)
            # Batches bound both parallel requests and pending futures.
            with ThreadPoolExecutor(max_workers=4) as pool:
                for start in range(2, pages + 1, 4):
                    for result in pool.map(fetch, range(start, min(start + 4, pages + 1))):
                        found.extend(result["books"])
        unique, seen = [], set()
        for book in found:
            isbn, work = book.get("isbn"), work_key(book["title"], book["author"])
            if (isbn and isbn in seen) or work in seen:
                continue
            if isbn:
                seen.add(isbn)
            seen.add(work)
            unique.append(book)
        unique.sort(key=title_key)
        with _cache_lock:
            _cache[key] = (time.monotonic() + 300, unique, corrected)
            _cache.move_to_end(key)
            while len(_cache) > 8:
                _cache.popitem(last=False)
        return unique, corrected


def order_books(books, sort):
    def numeric(value):
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return -1
    if sort == "popular":
        return sorted(books, key=lambda b: (-numeric(b.get("loan_count")), title_key(b)))
    if sort == "recent":
        return sorted(books, key=lambda b: (-numeric(b.get("publish_year")), title_key(b)))
    return sorted(books, key=title_key)


@router.get("/search")
def catalog_search(q: str = Query(min_length=1, max_length=500),
                   by: Literal["all", "title", "author", "isbn", "keyword"] = "title",
                   page: int = Query(1, ge=1),
                   sort: Literal["popular", "title", "recent"] = "popular"):
    q = q.strip()
    if not q:
        raise HTTPException(422, "검색어를 입력해주세요.")
    books, corrected = collect(q, by)
    books = order_books(books, sort)
    total = len(books)
    pages = math.ceil(total / PAGE_SIZE)
    current = min(page, max(1, pages))
    start = (current - 1) * PAGE_SIZE
    return {"query": q, "books": books[start:start + PAGE_SIZE], "total": total,
            "total_pages": pages, "page": current, "size": PAGE_SIZE,
            "total_is_estimate": False, "corrected_query": corrected, "sort": sort}
