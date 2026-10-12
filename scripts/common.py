"""스크립트 공통 설정: 경로, .env 로딩, MySQL 연결."""
import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "seed"
RAW_DIR = SEED_DIR / "raw"
BOOKS_JSONL = SEED_DIR / "books.jsonl"
INIT_SQL = ROOT / "db" / "init.sql"
load_dotenv(ROOT / ".env")


def _chroma_dir():
    """ChromaDB는 경로에 한글이 있으면 1,000건 이상일 때 인덱스를 다시 읽지 못한다.
    .env 의 CHROMA_DIR → 프로젝트 폴더(영문 경로일 때) → 홈 폴더 순으로 쓴다."""
    if os.environ.get("CHROMA_DIR"):
        return Path(os.environ["CHROMA_DIR"])
    for path in (ROOT / "chroma_data", Path.home() / ".readit" / "chroma_data"):
        if str(path).isascii():
            return path
    raise SystemExit("ChromaDB 경로에 한글이 없어야 합니다. .env 에 CHROMA_DIR=C:/readit_chroma 처럼 영문 경로를 지정하세요.")


CHROMA_DIR = _chroma_dir()


def env(name, default=None):
    value = os.environ.get(name, default)
    if value is None:
        raise SystemExit(f".env 에 {name} 값이 없습니다. .env.example 을 참고하세요.")
    return value


def get_mysql_connection(with_db=True):
    return pymysql.connect(
        host=env("MYSQL_HOST", "localhost"),
        port=int(env("MYSQL_PORT", "3306")),
        user=env("MYSQL_USER", "root"),
        password=env("MYSQL_PASSWORD"),
        database=env("MYSQL_DB", "read_it_db") if with_db else None,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
