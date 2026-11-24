"""Exercise community persistence functions with SQL-backed fixtures."""
import ast, importlib.util, sqlite3, unittest, re
from pathlib import Path
from datetime import datetime,timezone,timedelta
from fastapi import Depends,HTTPException,Query
from pydantic import BaseModel,Field
from typing import Literal
from enum import Enum
IntegrityError = sqlite3.IntegrityError
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('author_helper',ROOT/'routers/community_store.py')
store=importlib.util.module_from_spec(spec);spec.loader.exec_module(store)
class Cursor:
 def __init__(self,db):self.raw=db.cursor();self.rowcount=0;self.option_id=None
 def __enter__(self):return self
 def __exit__(self,*a):self.raw.close()
 @property
 def lastrowid(self):return self.option_id if self.option_id is not None else self.raw.lastrowid
 def execute(self,sql,args=()):
  self.option_id=None
  if 'ON DUPLICATE KEY UPDATE' in sql:
   table=re.search(r'INSERT INTO (\w+)',sql).group(1);column='category_id' if table=='post_category' else 'type_id'
   self.raw.execute(f'INSERT INTO {table} (name) VALUES (?) ON CONFLICT(name) DO UPDATE SET name=excluded.name RETURNING {column}',args)
   self.option_id=self.raw.fetchone()[0];self.rowcount=1
   return
  self.raw.execute(sql.replace('%s','?').removesuffix(' FOR UPDATE'),args);self.rowcount=self.raw.rowcount
  if self.raw.description:
   names=[x[0] for x in self.raw.description]
   assert len(names)==len(set(names)),f'Duplicate selected columns: {names}'
 def fetchall(self):return [dict(x) for x in self.raw.fetchall()]
 def fetchone(self):
  x=self.raw.fetchone();return dict(x) if x else None
class Connection:
 def __init__(self,raw):self.raw=raw
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def cursor(self):return Cursor(self.raw)
 def commit(self):self.raw.commit()
 def close(self):pass
from routers.one_line_reviews import (
    _REVIEW_REF_PREFIX, attach_review_reference, fetch_lines, remove_legacy_review_copies, split_review_reference,
)

class ActivityTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
  self.db.executescript('''
  CREATE TABLE users(user_id INT,public_id TEXT,nickname TEXT UNIQUE,is_suspended INT DEFAULT 0);
  INSERT INTO users(user_id,public_id,nickname) VALUES(1,'public1','기찬');
  CREATE TABLE post_category(category_id INTEGER PRIMARY KEY,name TEXT UNIQUE);
  INSERT INTO post_category VALUES(1,'talk'),(2,'share'),(3,'info');
  CREATE TABLE post_type(type_id INTEGER PRIMARY KEY,name TEXT UNIQUE);
  INSERT INTO post_type VALUES(1,'free'),(2,'quote'),(3,'line');
  CREATE TABLE community_post(post_id INTEGER PRIMARY KEY,user_id INT,category_id INT,post_type_id INT,title TEXT,content TEXT,has_spoiler INT,anonymous INT,created_at INTEGER DEFAULT 1763337600000);
  CREATE TABLE post_extra(post_id INTEGER PRIMARY KEY,isbn TEXT,quote TEXT,spoiler_stage TEXT,rating INT,recommend_verdict TEXT,created_at INTEGER DEFAULT 999);
  CREATE TABLE book(isbn TEXT,title TEXT,author TEXT,publisher TEXT,publish_year INT,cover_image_url TEXT);
  INSERT INTO book VALUES('9781234567890','책 제목','작가','출판사',2026,NULL);
  CREATE TABLE book_review(review_id INTEGER PRIMARY KEY,user_id INT,isbn TEXT,content TEXT,rating INT,has_spoiler INT,created_at INTEGER DEFAULT 1763337600000);
  CREATE TABLE post_comment(comment_id INT,post_id INT,user_id INT,content TEXT,created_at INT,deleted INT);
  CREATE TABLE post_like(post_id INT,user_id INT);
  CREATE TABLE polls(poll_id INT,post_id INT);
  CREATE TABLE poll_options(option_id INT,poll_id INT,label TEXT,position INT);
  CREATE TABLE poll_votes(user_id INT,poll_id INT,option_id INT);
  CREATE TABLE media(media_id INT,post_id INT,user_id INT,created_at INT);
  CREATE TABLE reading_record(user_id INT,isbn TEXT,progress TEXT,status TEXT);
  ''')
  names={'Book','SpoilerStage','PostInput','get_post','_post_option_id','get_post_category_id','get_post_type_id','progress_for','hidden_for','serialize_post','create_post','my_activity','feed','recommend_post','delete_post'}
  parsed=ast.parse((ROOT/'routers/community.py').read_text());nodes=[n for n in parsed.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
  for node in nodes:
   if isinstance(node,ast.FunctionDef):node.decorator_list=[]
  self.ns=dict(BaseModel=BaseModel,Field=Field,Literal=Literal,Enum=Enum,Depends=Depends,current_user=lambda:None,optional_user=lambda:None,Query=Query,IntegrityError=IntegrityError,
    datetime=datetime,KOREA=timezone(timedelta(hours=9)),HTTPException=HTTPException,ISBN=r'^(978|979)\d{10}$',database=lambda:Connection(self.db),db_user_id=lambda c,u:1,author_json=store.author_json,add_to_db=lambda isbn:isbn,taste_neighbors=lambda c,u:{},fetch_lines=fetch_lines, _REVIEW_REF_PREFIX=_REVIEW_REF_PREFIX,
    attach_review_reference=attach_review_reference, split_review_reference=split_review_reference)
  exec(compile(ast.Module(body=nodes,type_ignores=[]),'<community-test>','exec'),self.ns)
 def tearDown(self):self.db.close()
 def create(self,**patch):
  payload=self.ns['PostInput'](**dict(kind='free',category='talk',title='제목',body='내용',stage=0,**patch)) if not patch else self.ns['PostInput'](**({'kind':'free','category':'talk','title':'제목','body':'내용','stage':0}|patch))
  return self.ns['create_post'](payload,{'id':'google:test'})['post']
 def test_free_post_activity_preserves_id_and_timestamp(self):
  post=self.create();self.assertEqual(post['id'],1);self.assertEqual(post['createdAt'],1763337600000)
  activity=self.ns['my_activity']({'id':'google:test'})
  self.assertEqual(activity['counts'],{'posts':1,'comments':0,'lines':0});self.assertEqual(activity['posts'][0]['book'],{})
 def test_book_posts_activity_uses_catalog_and_verdict_is_correct(self):
  self.create(kind='quote',category='info',book={'isbn':'9781234567890','title':'책 제목'})
  self.assertEqual(self.db.execute('SELECT category_id FROM community_post').fetchone()[0],2)
  post=self.create(kind='line',book={'isbn':'9781234567890','title':'책 제목'},recommended=False)
  self.assertIs(post['recommended'],False)
  activity=self.ns['my_activity']({'id':'google:test'});self.assertEqual(activity['counts']['lines'],1);self.assertEqual(activity['counts']['posts'],1)
  self.assertEqual(activity['posts'][0]['book']['title'],'책 제목')
 def test_main_feed_excludes_lines_but_book_tab_can_query_them(self):
  self.create();self.create(kind='line',book={'isbn':'9781234567890','title':'책 제목'},recommended=True)
  args=dict(category='all',kind='all',mode='all',sort='recent',isbn=None,author=None,q='',page=1,user=None)
  # Feed count queries expose column aliases; SQLite supports these query forms.
  feed=self.ns['feed'](**args);self.assertEqual([p['kind'] for p in feed['posts']],['free'])
  feed=self.ns['feed'](**(args|{'kind':'line','isbn':'9781234567890'}));self.assertEqual([p['kind'] for p in feed['posts']],['line'])
 def test_missing_defaults_are_created_and_not_duplicated(self):
  self.db.executescript('DELETE FROM post_category;DELETE FROM post_type;')
  first=self.create()
  self.assertEqual(first['category'],'talk');self.assertEqual(first['kind'],'free')
  second=self.create()
  self.assertEqual(second['kind'],'free')
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM post_category').fetchone()[0],1)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM post_type').fetchone()[0],1)
  self.create(kind='quote',book={'isbn':'9781234567890','title':'책 제목'})
  self.create(kind='line',book={'isbn':'9781234567890','title':'책 제목'},recommended=True)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM post_type').fetchone()[0],3)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM community_post').fetchone()[0],4)
 def test_bad_lookup_value_does_not_write_data(self):
  before=self.db.total_changes
  with self.assertRaises(HTTPException) as result:
   self.ns['get_post_category_id'](Cursor(self.db),'invalid')
  self.assertEqual(result.exception.status_code,422)
  self.assertEqual(self.db.total_changes,before)
 def test_concurrent_insert_returns_existing_identifier(self):
  class ConcurrentCursor:
   lastrowid=42
   def execute(self,sql,args):self.sql=sql
   def fetchone(self):return None
  cursor=ConcurrentCursor()
  self.assertEqual(self.ns['get_post_category_id'](cursor,'talk'),42)
  self.assertIn('ON DUPLICATE KEY UPDATE category_id=LAST_INSERT_ID(category_id)',cursor.sql)
 def test_activity_counts_and_lists_book_comments_as_one_line_reviews(self):
  self.create(kind='line',book={'isbn':'9781234567890','title':'책 제목'},body='같은 한줄평',recommended=True)
  self.db.execute("INSERT INTO book_review(user_id,isbn,content,rating,has_spoiler) VALUES(1,'9781234567890','같은 한줄평',5,0),(1,'9781234567890','또 다른 감상',4,0)")
  activity=self.ns['my_activity']({'id':'google:test'})
  self.assertEqual(activity['counts'],{'posts':0,'comments':0,'lines':2})
  self.assertEqual({line['body'] for line in activity['lines']},{'같은 한줄평','또 다른 감상'})

 def test_share_filter_excludes_reviews_and_recommendation_toggles(self):
  free = self.create(category='share')
  quote = self.create(kind='quote', book={'isbn':'9781234567890','title':'책 제목'})
  args = dict(category='share', kind='all', mode='all', sort='recent', isbn=None,
              author=None, q='', page=1, user=None)
  self.assertEqual([p['id'] for p in self.ns['feed'](**args)['posts']], [free['id']])
  toggle = self.ns['recommend_post']
  for user_id in (1, 2):
   self.ns['db_user_id'] = lambda cursor, user: user_id
   added = toggle(quote['id'], {'id':'google:test'})['post']
   self.assertEqual((added['recommendCount'], added['recommendedByMe']), (1, True))
   removed = toggle(quote['id'], {'id':'google:test'})['post']
   self.assertEqual((removed['recommendCount'], removed['recommendedByMe']), (0, False))

 def test_deleted_review_leaves_community_body_and_disappears_from_review_lists(self):
  isbn = '9781234567890'
  book = {'isbn':isbn, 'title':'책 제목'}
  self.db.execute("INSERT INTO book_review(user_id,isbn,content,rating,has_spoiler) VALUES(1,?,'독서 한줄평',5,1)", (isbn,))
  post = self.create(kind='quote', book=book, body='게시글 내용', attachReview=True, hasSpoiler=True)
  old = self.create(kind='quote', book=book, body='독서 한줄평', rating=5)
  self.create(kind='line', book=book, body='독서 한줄평', recommended=True)
  self.assertEqual(post['linkedReview'], {'body':'독서 한줄평', 'rating':5})
  hidden = self.ns['serialize_post'](Cursor(self.db), self.ns['get_post'](Cursor(self.db), post['id']), None)
  self.assertIsNone(hidden['linkedReview'])
  remove_legacy_review_copies(Cursor(self.db), 1, isbn, '독서 한줄평', 5)
  self.db.execute('DELETE FROM book_review WHERE user_id=1 AND isbn=?', (isbn,))
  activity = self.ns['my_activity']({'id':'google:test'})
  by_id = {p['id']:p for p in activity['posts']}
  self.assertEqual(by_id[post['id']]['body'], '게시글 내용')
  self.assertIsNone(by_id[post['id']]['linkedReview'])
  self.assertEqual(by_id[old['id']]['body'], '')
  self.assertIsNone(by_id[old['id']]['rating'])
  self.assertEqual(activity['lines'], [])
  self.assertEqual(fetch_lines(Cursor(self.db), random_limit=5), [])

 def test_only_author_can_delete_even_when_using_a_pen_name(self):
  author = {'id': 'google:author'}
  reader = {'id': 'google:reader'}
  self.ns['db_user_id'] = lambda cursor, user: 2 if user == reader else 1
  post = self.create(anonymous=True)
  delete = self.ns['delete_post']

  with self.assertRaises(HTTPException) as rejected:
   delete(post['id'], reader)
  self.assertEqual(rejected.exception.status_code, 403)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM community_post').fetchone()[0], 1)
  self.assertEqual(delete(post['id'], author), {'ok': True})
  with self.assertRaises(HTTPException) as missing:
   delete(post['id'], author)
  self.assertEqual(missing.exception.status_code, 404)

if __name__=='__main__':unittest.main()
