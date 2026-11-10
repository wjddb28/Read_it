"""Community persistence, isolated from the teammate-owned MySQL schema."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
    );
    
CREATE TABLE IF NOT EXISTS profiles (
 owner TEXT PRIMARY KEY, 
 public_id TEXT NOT NULL UNIQUE, 
 nickname TEXT NOT NULL,
 nickname_key TEXT NOT NULL UNIQUE, 
 bio TEXT NOT NULL DEFAULT '', 
 liked TEXT NOT NULL DEFAULT '[]',
 disliked TEXT NOT NULL DEFAULT '[]', 
 onboarded INTEGER NOT NULL DEFAULT 0
 );
 
CREATE TABLE IF NOT EXISTS reading (
 owner TEXT NOT NULL REFERENCES profiles(owner), 
 isbn TEXT NOT NULL, 
 book TEXT NOT NULL,
 rating INTEGER NOT NULL DEFAULT 0 CHECK(rating BETWEEN 0 AND 5), 
 status TEXT NOT NULL,
 progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 2), 
 genres TEXT NOT NULL DEFAULT '[]',
 PRIMARY KEY(owner,isbn)
 );
 
CREATE TABLE IF NOT EXISTS posts (
 id TEXT PRIMARY KEY, 
 owner TEXT NOT NULL REFERENCES profiles(owner), 
 kind TEXT NOT NULL,
 category TEXT NOT NULL, 
 title TEXT NOT NULL, 
 body TEXT NOT NULL, 
 quote TEXT NOT NULL DEFAULT '',
 isbn TEXT, 
 book TEXT, 
 rating INTEGER, 
 recommended INTEGER, 
 stage INTEGER NOT NULL DEFAULT 0,
 anonymous INTEGER NOT NULL DEFAULT 0, 
 has_spoiler INTEGER NOT NULL DEFAULT 0, 
 created_at INTEGER NOT NULL
 );
 
CREATE INDEX IF NOT EXISTS posts_feed ON posts(created_at DESC);
CREATE INDEX IF NOT EXISTS posts_book ON posts(isbn,kind);
CREATE UNIQUE INDEX IF NOT EXISTS one_line_per_reader ON posts(owner,isbn) WHERE kind='line';

CREATE TABLE IF NOT EXISTS comments (
 id TEXT PRIMARY KEY, 
 post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
 owner TEXT NOT NULL REFERENCES profiles(owner), 
 parent_id TEXT REFERENCES comments(id),
 body TEXT NOT NULL, 
 anonymous INTEGER NOT NULL DEFAULT 0, 
 deleted INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL
 );
 
CREATE TABLE IF NOT EXISTS endorsements (
 post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
 owner TEXT NOT NULL REFERENCES profiles(owner), 
 created_at INTEGER NOT NULL,
 PRIMARY KEY(post_id,owner)
 );
 
CREATE TABLE IF NOT EXISTS polls (
 id TEXT PRIMARY KEY, 
 post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
 label TEXT NOT NULL, 
 position INTEGER NOT NULL
 );
 
CREATE TABLE IF NOT EXISTS votes (
 post_id TEXT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
 owner TEXT NOT NULL REFERENCES profiles(owner), 
 option_id TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
 PRIMARY KEY(post_id,owner)
 );
 
CREATE TABLE IF NOT EXISTS follows (
 follower TEXT NOT NULL REFERENCES profiles(owner), 
 target TEXT NOT NULL REFERENCES profiles(owner),
 PRIMARY KEY(follower,target)
 );
 
CREATE TABLE IF NOT EXISTS media (
 id TEXT PRIMARY KEY, 
 owner TEXT NOT NULL REFERENCES profiles(owner),
 post_id TEXT REFERENCES posts(id) ON DELETE CASCADE, 
 data BLOB NOT NULL, 
 created_at INTEGER NOT NULL
 );
"""


def db_path():
    return Path(os.getenv('READIT_COMMUNITY_DB') or Path.home() / '.readit' / 'community.sqlite3')


@contextmanager
def database():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript(SCHEMA)
    try:
        conn.execute('BEGIN IMMEDIATE')
        # Preserve older community records while enabling explicit spoiler labels.
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(posts)')}
        if 'has_spoiler' not in columns:
            conn.execute('ALTER TABLE posts ADD COLUMN has_spoiler INTEGER NOT NULL DEFAULT 0')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now():
    return int(time.time() * 1000)


def key(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


def ensure_profile(conn, user):
    row = conn.execute('SELECT * FROM profiles WHERE owner=?', (user['id'],)).fetchone()
    if row:
        return row
    public_id = secrets.token_hex(16)
    nickname = '독자' + public_id[:8]
    conn.execute('INSERT INTO profiles(owner,public_id,nickname,nickname_key) VALUES(?,?,?,?)',
                 (user['id'], public_id, nickname, key(nickname)))
    return conn.execute('SELECT * FROM profiles WHERE owner=?', (user['id'],)).fetchone()


def profile_json(row):
    return {'profileId': row['public_id'], 'nickname': row['nickname'], 'bio': row['bio'],
            'likedGenres': json.loads(row['liked']), 'dislikedGenres': json.loads(row['disliked']),
            'onboarded': bool(row['onboarded'])}


def author_json(conn, owner, isbn=None, anonymous=False):
    if anonymous:
        secret = conn.execute("SELECT value FROM settings WHERE key='alias_secret'").fetchone()
        if not secret:
            value = secrets.token_hex(32)
            conn.execute("INSERT INTO settings(key,value) VALUES('alias_secret',?)", (value,))
        else:
            value = secret['value']
        digest = hmac.new(value.encode(), (owner + '\0' + (isbn or '')).encode(), hashlib.sha256).hexdigest()
        return {'nickname': '책갈피 ' + digest[:8], 'profileId': None, 'anonymous': True}
    row = conn.execute('SELECT public_id,nickname FROM profiles WHERE owner=?', (owner,)).fetchone()
    return {'nickname': row['nickname'], 'profileId': row['public_id'], 'anonymous': False}
