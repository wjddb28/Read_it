"""Run endpoint SQL against a lightweight test database; no production DB writes."""
import ast
from pathlib import Path
import importlib.util
import logging
import random
import re
import sqlite3
import unittest
from routers.one_line_reviews import fetch_lines
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('community_store_for_test', ROOT / 'routers/community_store.py')
store = importlib.util.module_from_spec(spec); spec.loader.exec_module(store)

class Cursor:
    def __init__(self, raw): self.cursor = raw.cursor()
    def __enter__(self): return self
    def __exit__(self, *args): self.cursor.close()
    def execute(self, sql, args=()): self.cursor.execute(sql.replace('%s', '?'), args)
    def fetchall(self): return [dict(row) for row in self.cursor.fetchall()]
    def fetchone(self):
        row = self.cursor.fetchone(); return dict(row) if row else None
class Connection:
    def __init__(self, raw): self.raw = raw
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return Cursor(self.raw)

class RandomLinesTests(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(':memory:', check_same_thread=False)
        self.raw.row_factory = sqlite3.Row; self.raw.create_function('RAND', 0, random.random)
        self.raw.executescript('''
          CREATE TABLE users(user_id INTEGER PRIMARY KEY,public_id TEXT,nickname TEXT,is_suspended INT);
          CREATE TABLE post_type(type_id INTEGER PRIMARY KEY,name TEXT);
          CREATE TABLE community_post(post_id INTEGER PRIMARY KEY,user_id INT,post_type_id INT,content TEXT,anonymous INT,has_spoiler INT,created_at INTEGER DEFAULT 1763337600000);
          CREATE TABLE post_extra(post_id INTEGER PRIMARY KEY,isbn TEXT,recommend_verdict TEXT,spoiler_stage TEXT,rating INT);
          CREATE TABLE book(isbn TEXT PRIMARY KEY,title TEXT,author TEXT);
          CREATE TABLE book_review(review_id INTEGER PRIMARY KEY,user_id INT,isbn TEXT,content TEXT,rating INT,has_spoiler INT,created_at INTEGER DEFAULT 1763337600000);
          INSERT INTO users VALUES(1,'reader-id','독자',0),(2,'blocked','정지 계정',1);
          INSERT INTO post_type VALUES(1,'line'),(2,'free');
          INSERT INTO book VALUES('9781234567890','책 제목','작가');
        ''')
        source = ast.parse((ROOT / 'routers/community.py').read_text())
        nodes = [n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in {'random_lines','book_lines'}]
        for node in nodes: node.decorator_list = []
        namespace = dict(Response=Response, HTTPException=HTTPException, database=lambda: Connection(self.raw), author_json=store.author_json, logging=logging, fetch_lines=fetch_lines, re=re, ISBN=r'^(978|979)\d{10}$')
        exec(compile(ast.Module(body=nodes,type_ignores=[]), '<random_lines>', 'exec'), namespace)
        self.app = FastAPI(); self.app.get('/api/community/random-lines')(namespace['random_lines'])
        self.app.get('/api/community/books/{isbn}/lines')(namespace['book_lines'])
        self.client = TestClient(self.app)
    def tearDown(self): self.raw.close()
    def add(self, id, kind=1, content='한줄평', anonymous=0, spoiler=0, stage='EARLY', user=1, verdict='RECOMMEND'):
        self.raw.execute('INSERT INTO community_post(post_id,user_id,post_type_id,content,anonymous,has_spoiler) VALUES(?,?,?,?,?,?)',(id,user,kind,content,anonymous,spoiler))
        self.raw.execute('INSERT INTO post_extra(post_id,isbn,recommend_verdict,spoiler_stage) VALUES(?,?,?,?)',(id,'9781234567890',verdict,stage));self.raw.commit()
    def test_empty_and_fewer_than_five(self):
        response=self.client.get('/api/community/random-lines')
        self.assertEqual(response.json(),{'lines':[]});self.assertEqual(response.headers['cache-control'],'no-store')
        self.add(1,verdict='NOT_RECOMMEND')
        line=self.client.get('/api/community/random-lines').json()['lines'][0]
        self.assertFalse(line['recommended']);self.assertEqual(line['book']['title'],'책 제목')
    def test_random_sample_excludes_hidden_and_preserves_pseudonyms(self):
        for id in range(1,11):self.add(id,content=f'한줄평 {id}',anonymous=id==1,verdict=None if id==1 else 'RECOMMEND')
        self.add(11,spoiler=1);self.add(12,stage='MID');self.add(13,kind=2);self.add(14,content='   ');self.add(15,user=2)
        samples=set(); seen_anon=False
        for _ in range(30):
            lines=self.client.get('/api/community/random-lines').json()['lines']
            ids=[int(line['id'].split(':')[1]) for line in lines]
            self.assertEqual(len(set(ids)),5);self.assertTrue(set(ids)<=set(range(1,11)))
            samples.add(tuple(ids))
            for line in lines:
                if line['id']=='post:1':
                    seen_anon=True;self.assertIsNone(line['author']['profileId']);self.assertNotEqual(line['author']['nickname'],'독자');self.assertIsNone(line['recommended'])
        self.assertGreater(len(samples),1)
        # Deterministically test the anonymous-only case too.
        self.raw.execute('DELETE FROM community_post WHERE post_id<>1');self.raw.commit()
        line=self.client.get('/api/community/random-lines').json()['lines'][0]
        self.assertIsNone(line['author']['profileId']);self.assertTrue(line['author']['anonymous'])

    def test_book_comments_are_included_and_identical_public_entries_are_deduplicated(self):
        self.add(1,content='같은 감상')
        self.add(2,content='예전 한줄평')
        self.raw.execute("INSERT INTO book_review(review_id,user_id,isbn,content,rating,has_spoiler) VALUES(1,1,'9781234567890','같은 감상',5,0),(2,1,'9781234567890','스포일러',4,1),(3,1,'9781234567890','   ',3,0)")
        lines=self.client.get('/api/community/random-lines').json()['lines']
        self.assertEqual({line['body'] for line in lines},{'같은 감상','예전 한줄평'})
        self.assertEqual(next(line for line in lines if line['body']=='같은 감상')['id'],'review:1')
        all_lines=fetch_lines(Cursor(self.raw),isbn='9781234567890')
        self.assertEqual(len(all_lines),3)
        self.assertTrue(next(line for line in all_lines if line['body']=='스포일러')['hasSpoiler'])
        self.assertEqual(fetch_lines(Cursor(self.raw),isbn='9791234567890'),[])

    def test_book_detail_endpoint_uses_unified_source_and_validates_isbn(self):
        self.add(1,content='예전 한줄평',spoiler=1)
        self.raw.execute("INSERT INTO book_review(review_id,user_id,isbn,content,rating,has_spoiler) VALUES(1,1,'9781234567890','예전 코멘트',5,0)")
        response=self.client.get('/api/community/books/9781234567890/lines')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual({line['body'] for line in response.json()['lines']},{'예전 코멘트','예전 한줄평'})
        self.assertEqual(self.client.get('/api/community/books/invalid/lines').status_code,422)

if __name__=='__main__':unittest.main()
