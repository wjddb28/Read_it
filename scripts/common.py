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
CHROMA_DIR = ROOT / "chroma_data"

load_dotenv(ROOT / ".env")


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
