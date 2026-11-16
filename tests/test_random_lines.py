"""Run endpoint SQL against a lightweight test database; no production DB writes."""
import ast
from pathlib import Path
import importlib.util
import logging
import random
import sqlite3
import unittest
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
          CREATE TABLE community_post(post_id INTEGER PRIMARY KEY,user_id INT,post_type_id INT,content TEXT,anonymous INT,has_spoiler INT);
          CREATE TABLE post_extra(post_id INTEGER PRIMARY KEY,isbn TEXT,recommend_verdict TEXT,spoiler_stage TEXT);
          CREATE TABLE book(isbn TEXT PRIMARY KEY,title TEXT,author TEXT);
          INSERT INTO users VALUES(1,'reader-id','독자',0),(2,'blocked','정지 계정',1);
          INSERT INTO post_type VALUES(1,'line'),(2,'free');
          INSERT INTO book VALUES('9781234567890','책 제목','작가');
        ''')
        source = ast.parse((ROOT / 'routers/community.py').read_text())
        node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'random_lines')
        node.decorator_list = []
        namespace = dict(Response=Response, HTTPException=HTTPException, database=lambda: Connection(self.raw), author_json=store.author_json, logging=logging)
        exec(compile(ast.Module(body=[node],type_ignores=[]), '<random_lines>', 'exec'), namespace)
        self.app = FastAPI(); self.app.get('/api/community/random-lines')(namespace['random_lines'])
        self.client = TestClient(self.app)
    def tearDown(self): self.raw.close()
    def add(self, id, kind=1, content='한줄평', anonymous=0, spoiler=0, stage='EARLY', user=1, verdict='RECOMMEND'):
        self.raw.execute('INSERT INTO community_post VALUES(?,?,?,?,?,?)',(id,user,kind,content,anonymous,spoiler))
        self.raw.execute('INSERT INTO post_extra VALUES(?,?,?,?)',(id,'9781234567890',verdict,stage));self.raw.commit()
    def test_empty_and_fewer_than_five(self):
        response=self.client.get('/api/community/random-lines')
        self.assertEqual(response.json(),{'lines':[]});self.assertEqual(response.headers['cache-control'],'no-store')
        self.add(1,verdict='NOT_RECOMMEND')
        line=self.client.get('/api/community/random-lines').json()['lines'][0]
        self.assertFalse(line['recommended']);self.assertEqual(line['book']['title'],'책 제목')
    def test_random_sample_excludes_hidden_and_preserves_pseudonyms(self):
        for id in range(1,11):self.add(id,anonymous=id==1,verdict=None if id==1 else 'RECOMMEND')
        self.add(11,spoiler=1);self.add(12,stage='MID');self.add(13,kind=2);self.add(14,content='   ');self.add(15,user=2)
        samples=set(); seen_anon=False
        for _ in range(30):
            lines=self.client.get('/api/community/random-lines').json()['lines']
            ids=[line['id'] for line in lines]
            self.assertEqual(len(set(ids)),5);self.assertTrue(set(ids)<=set(range(1,11)))
            samples.add(tuple(ids))
            for line in lines:
                if line['id']==1:
                    seen_anon=True;self.assertIsNone(line['author']['profileId']);self.assertNotEqual(line['author']['nickname'],'독자');self.assertIsNone(line['recommended'])
        self.assertGreater(len(samples),1)
        # Deterministically test the anonymous-only case too.
        self.raw.execute('DELETE FROM community_post WHERE post_id<>1');self.raw.commit()
        line=self.client.get('/api/community/random-lines').json()['lines'][0]
        self.assertIsNone(line['author']['profileId']);self.assertTrue(line['author']['anonymous'])

if __name__=='__main__':unittest.main()
