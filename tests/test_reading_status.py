"""Exercise the actual library routes without a production MySQL connection."""
import ast
from datetime import date
import logging
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
from typing import Literal
import unittest

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


class Cursor:
    def __init__(self, connection): self.raw = connection.cursor()
    def __enter__(self): return self
    def __exit__(self, *args): self.raw.close()
    def execute(self, sql, values=()): self.raw.execute(sql.replace('%s', '?'), values)
    def fetchone(self):
        row = self.raw.fetchone()
        return dict(row) if row else None
    def fetchall(self): return [dict(row) for row in self.raw.fetchall()]


class Connection:
    def __init__(self, raw): self.raw = raw
    def cursor(self): return Cursor(self.raw)
    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()
    def close(self): pass


class ReadingStatusTests(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(':memory:', detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
        self.raw.row_factory = sqlite3.Row
        self.raw.executescript('''
            CREATE TABLE book(isbn TEXT PRIMARY KEY,title TEXT,author TEXT,publisher TEXT,
                              publish_year INT,description TEXT,cover_image_url TEXT);
            INSERT INTO book(isbn,title) VALUES('9781234567890','테스트 도서');
            CREATE TABLE reading_record(record_id INTEGER PRIMARY KEY,user_id INT,isbn TEXT,
                status TEXT DEFAULT 'READING',start_date DATE DEFAULT '2026-01-01',
                end_date DATE DEFAULT '2026-01-02',progress TEXT,UNIQUE(user_id,isbn));
            CREATE TABLE daily_reading_log(record_id INT,log_date DATE,content TEXT,reading_minutes INT);
        ''')
        source = ast.parse((Path(__file__).resolve().parents[1] / 'routers/library.py').read_text())
        names = {'ReadingUpdate','AddBook','fetch_daily_logs','fetch_record','serialize_record',
                 'validate_update','add_library_book','update_library_book'}
        nodes = [n for n in source.body if isinstance(n, (ast.ClassDef,ast.FunctionDef)) and n.name in names]
        for node in nodes:
            if isinstance(node,ast.FunctionDef): node.decorator_list = []
        ns = dict(BaseModel=BaseModel,Field=Field,Literal=Literal,date=date,Depends=Depends,
                  current_user=lambda: {'id':'google:test'},HTTPException=HTTPException,
                  ISBN_PATTERN=re.compile(r'^(978|979)\d{10}$'),
                  BOOK_COLUMNS='b.title,b.author,b.publisher,b.publish_year,b.description,b.cover_image_url',
                  connection=lambda:Connection(self.raw),db_user_id=lambda cursor,user:1,
                  add_to_db=lambda isbn:isbn,logger=logging.getLogger('test'),
                  pymysql=SimpleNamespace(MySQLError=sqlite3.DatabaseError,
                      err=SimpleNamespace(IntegrityError=sqlite3.IntegrityError)))
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<library routes>','exec'),ns)
        self.ns = ns
        app = FastAPI()
        app.post('/api/library')(ns['add_library_book'])
        app.put('/api/library/{isbn}')(ns['update_library_book'])
        self.client = TestClient(app)

    def tearDown(self): self.raw.close()

    def add(self): return self.client.post('/api/library',json={'isbn':'9781234567890'})
    def update(self, **patch): return self.client.put('/api/library/9781234567890',json=patch)

    def test_new_book_is_wish_without_dates_even_if_database_defaults_differ(self):
        response = self.add()
        self.assertEqual(response.status_code,200)
        record = response.json()['record']
        self.assertEqual((record['status'],record['startDate'],record['endDate']),('WISH','',''))
        row = self.raw.execute('SELECT start_date,end_date FROM reading_record').fetchone()
        self.assertEqual(tuple(row),(None,None))

    def test_frontend_payload_saves_without_progress_for_both_active_states(self):
        self.add()
        for status in ('READING','COMPLETED'):
            response = self.update(status=status,startDate='2026-11-13',endDate='2026-11-16')
            self.assertEqual(response.status_code,200,response.text)
            record = response.json()['record']
            self.assertEqual((record['status'],record['startDate'],record['endDate']),
                             (status,'2026-11-13','2026-11-16'))

    def test_wish_clears_dates_even_when_a_client_sends_stale_reversed_values(self):
        self.add()
        self.update(status='COMPLETED',startDate='2026-11-13',endDate='2026-11-16')
        response = self.update(status='WISH',startDate='2026-11-16',endDate='2026-11-13')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['record']['startDate'],'')
        self.assertEqual(response.json()['record']['endDate'],'')

    def test_reverse_dates_are_rejected_without_changing_saved_record(self):
        self.add()
        response = self.update(status='READING',startDate='2026-11-16',endDate='2026-11-13')
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.raw.execute('SELECT status FROM reading_record').fetchone()[0],'WISH')

    def test_active_dates_are_optional_and_missing_books_return_404(self):
        self.assertEqual(self.update(status='READING').status_code,404)
        self.add()
        response = self.update(status='READING',startDate=None,endDate=None)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['record']['startDate'],'')


if __name__ == '__main__': unittest.main()
