"""Authenticated community APIs. No writes to the existing MySQL database."""
import base64
import binascii
from enum import Enum
import io
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from pymysql import IntegrityError

from common import get_mysql_connection
from routers.auth import current_user, check_origin
from routers.books import add_to_db
from routers.community_store import author_json
from routers.one_line_reviews import attach_review_reference, fetch_lines, split_review_reference, _REVIEW_REF_PREFIX
from routers.library import db_user_id
from routers.profile import fetch_genre_preferences, fetch_library_stats

router = APIRouter(prefix='/api/community', tags=['community'])
KOREA = timezone(timedelta(hours=9))
ISBN = r'^(978|979)\d{10}$'

def database():
    """Create a MySQL database connection."""
    try:
        return get_mysql_connection()
    except Exception as e:
        raise RuntimeError("Could not connect to MySQL database. Please check your configuration.") from e

def optional_user(request: Request):
    try:
        return current_user(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise


class Book(BaseModel):
    isbn: str = Field(pattern=ISBN, default="")
    title: str = Field(min_length=1, max_length=255)
    author: str = Field(default='', max_length=255)
    cover_image_url: str | None = Field(default=None, max_length=1000)
    genres: list[str] = Field(default_factory=list, max_length=40)

class SpoilerStage(Enum):
    EARLY = 0
    MID = 1
    LATE = 2

class PostInput(BaseModel):
    #quote, book, rating, recommended, stage are all stored in post_extra table
    kind: Literal['free', 'quote', 'line'] = 'quote'
    #kind is stored as post_type table in db
    category: Literal['talk', 'share', 'info'] = 'share'
    #stored as post_category table in db
    title: str = Field(default='', max_length=120)
    body: str = Field(default="", max_length=3000)
    attachReview: bool = False
    quote: str = Field(default='', max_length=300)
    book: Book | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    recommended: bool | None = None
    stage: SpoilerStage
    #spoiler stage (EARLY, MID, LATE)
    hasSpoiler: bool = False
    anonymous: bool = False
    images: list[int] = Field(default_factory=list, max_length=3)
    poll: list[str] = Field(default_factory=list, max_length=6)


class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    parentId: int | None = Field(default=None, gt=0)
    anonymous: bool = False


class VoteInput(BaseModel):
    optionId: int = Field(gt=0)


class ImageInput(BaseModel):
    data: str = Field(min_length=1, max_length=4300000)


class ProgressInput(BaseModel):
    progress: int = Field(ge=0, le=2)

def get_post(cursor, post_id):
    cursor.execute("""SELECT p.*, e.isbn, e.quote, e.spoiler_stage, e.spoiler_stage AS stage, e.rating, e.recommend_verdict,
                          pt.name AS kind, pc.name AS category
                   FROM community_post AS p
                   LEFT JOIN post_extra AS e ON p.post_id = e.post_id
                   LEFT JOIN post_type AS pt ON p.post_type_id = pt.type_id
                   LEFT JOIN post_category AS pc ON p.category_id = pc.category_id
                   WHERE p.post_id = %s""", (post_id,))
    post = cursor.fetchone()
    if not post:
        raise HTTPException(404, '게시물을 찾을 수 없어요.')
    return post

def _post_option_id(cursor, name, option_type):
    # Identifiers come only from this fixed mapping, never from request input.
    options = {
        'category': ('post_category', 'category_id', {'talk', 'share', 'info'}),
        'type': ('post_type', 'type_id', {'free', 'quote', 'line'}),
    }
    table, id_column, allowed = options[option_type]
    if name not in allowed:
        raise HTTPException(422, '올바른 주제와 글 형식을 선택해주세요.')
    cursor.execute(f"SELECT {id_column} FROM {table} WHERE name = %s", (name,))
    row = cursor.fetchone()
    if row:
        return row[id_column]
    # Recover missing defaults in the same transaction as the new post.
    # LAST_INSERT_ID also returns the existing ID if another writer added it.
    cursor.execute(
        f"INSERT INTO {table} (name) VALUES (%s) "
        f"ON DUPLICATE KEY UPDATE {id_column}=LAST_INSERT_ID({id_column})",
        (name,),
    )
    return cursor.lastrowid


def get_post_category_id(cursor, category):
    return _post_option_id(cursor, category, 'category')


def get_post_type_id(cursor, post_type):
    return _post_option_id(cursor, post_type, 'type')


def progress_for(conn, user_id, isbn):
    if not user_id or not isbn:
        return 0
    conn.execute('SELECT progress,status FROM reading_record WHERE user_id=%s AND isbn=%s', (user_id, isbn,))
    row = conn.fetchone()
    if not row:
        return 0
    if row['status'] == 'COMPLETED':
        return 2
    return {'EARLY': 0, 'MID': 1, 'LATE': 2}.get(row['progress'], 0)


def hidden_for(conn, post, user_id, reveal=False):
    if reveal or post.get('kind') == 'line' or user_id == post['user_id']:
        return False
    stage = {'EARLY': 0, 'MID': 1, 'LATE': 2}.get(post['stage'], post['stage'])
    return bool(post['has_spoiler'] or (post['isbn'] and stage is not None and stage > progress_for(conn, user_id, post['isbn'])))


def serialize_post(cursor, post, user_id, reveal=False):
    post_id = post['post_id']
    own = bool(user_id == post['user_id'])
    hidden = hidden_for(cursor, post, user_id, reveal)

    linked_review = None
    body = None
    if not hidden:
        review_id, body = split_review_reference(post['content'])
        if review_id is not None:
            cursor.execute(
                "SELECT content, rating FROM book_review WHERE review_id=%s AND user_id=%s AND isbn=%s",
                (review_id, post['user_id'], post['isbn']),
            )
            review = cursor.fetchone()
            if review and (review['content'] or '').strip():
                linked_review = {'body': review['content'], 'rating': review['rating']}

    book = {}
    if post['isbn'] is not None:
        cursor.execute('SELECT isbn,title,author,publisher,publish_year,cover_image_url FROM book WHERE isbn=%s', (post['isbn'],))
        book = cursor.fetchone() or {}

    cursor.execute('SELECT COUNT(*) AS total FROM post_like WHERE post_id=%s', (post_id,))
    count = cursor.fetchone()['total']
    cursor.execute('SELECT COUNT(*) AS total FROM post_comment WHERE post_id=%s AND deleted=0', (post_id,))
    comment_count = cursor.fetchone()['total']
    cursor.execute('SELECT 1 FROM post_like WHERE post_id=%s AND user_id=%s', (post_id, user_id,))
    endorsed = bool(cursor.fetchone())
    poll = None
    images = []
    if not hidden:
        cursor.execute("""SELECT p.poll_id, o.option_id AS id, o.label, o.position,
                                  COUNT(v.user_id) AS votes
                           FROM polls AS p
                           JOIN poll_options AS o ON o.poll_id = p.poll_id
                           LEFT JOIN poll_votes AS v
                             ON v.poll_id = p.poll_id AND v.option_id = o.option_id
                           WHERE p.post_id = %s
                           GROUP BY p.poll_id, o.option_id, o.label, o.position
                           ORDER BY p.poll_id, o.position""", (post_id,))
        options = cursor.fetchall()
        if options:
            vote = None
            if user_id:
                cursor.execute("""SELECT v.option_id
                                  FROM poll_votes AS v
                                  JOIN polls AS p ON p.poll_id = v.poll_id
                                  WHERE p.post_id = %s AND v.user_id = %s
                                  ORDER BY p.poll_id
                                  LIMIT 1""", (post_id, user_id))
                vote = cursor.fetchone()
            poll = {
                'options': [dict(o) for o in options],
                'total': sum(o['votes'] for o in options),
                'myVote': vote['option_id'] if vote else None
                }

        cursor.execute('SELECT media_id FROM media WHERE post_id=%s ORDER BY created_at,media_id', (post_id,))
        for row in cursor.fetchall():
            images.append({'id': row['media_id']})

    kind = post.get('kind') or post.get('post_type_id')
    category = post.get('category') or post.get('category_id')
    return {'id': post_id,
            'kind': kind,
            'category': category,
            'title': '스포일러가 포함된 글' if hidden else post['title'],
            'body': body,
            'linkedReview': linked_review,
            'quote': None if hidden else post['quote'],
            'book': book,
            'rating': None if hidden else post['rating'],
            'recommended': None if hidden or post['recommend_verdict'] is None else post['recommend_verdict'] == 'RECOMMEND',
            'stage': {'EARLY': 0, 'MID': 1, 'LATE': 2}.get(post['spoiler_stage']),
            'hasSpoiler': bool(kind != 'line' and post['has_spoiler']),
            'spoilerHidden': hidden,
            'author': author_json(
                cursor, post['user_id'], post['isbn'], bool(post['anonymous']),
                post_id=post['post_id'],
            ),
            'own': own,
            'createdAt': post['created_at'],
            'recommendCount': count,
            'recommendedByMe': endorsed,
            'commentCount': comment_count,
            'images': images,
            'poll': poll
            }


@router.put('/progress/{isbn}', dependencies=[Depends(check_origin)])
def update_progress(isbn: str, payload: ProgressInput, user=Depends(current_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute('UPDATE reading_record SET progress=%s WHERE user_id=%s AND isbn=%s', (SpoilerStage(payload.progress).name, user_id, isbn))
            if not cursor.rowcount:
                raise HTTPException(404, '서재를 먼저 불러온 뒤 진도를 설정해주세요.')
            conn.commit()
        return {'progress': payload.progress}

@router.post('/images', dependencies=[Depends(check_origin)])
def upload_image(payload: ImageInput, user=Depends(current_user)):
    try:
        if not re.match(r'^data:image/(jpeg|png|webp);base64,', payload.data):
            raise ValueError('format')
        raw = base64.b64decode(payload.data.split(',', 1)[1], validate=True)
        if len(raw) > 3 * 1024 * 1024:
            raise ValueError('size')
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('JPEG', 'PNG', 'WEBP') or source.width * source.height > 16000000:
                raise ValueError('format')
            source.load()
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((1600, 1600))
            target = io.BytesIO()
            image.save(target, format='JPEG', quality=86)
            encoded = target.getvalue()
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, '사진은 3MB 이하의 JPG·PNG·WebP 파일로 올려주세요.') from exc
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            # Unattached uploads are private and removed after a day.
            cursor.execute('DELETE FROM media WHERE post_id IS NULL AND created_at<%s', (datetime.now() - timedelta(days=1),))
            conn.commit()
            cursor.execute('SELECT COUNT(*) AS counts FROM media WHERE user_id=%s AND post_id IS NULL', (user_id,))
            count_row = cursor.fetchone()
            if count_row is None:
                raise HTTPException(404, "사진의 개수를 카운트하지 못했어요.")
            count = count_row['counts']
            if count >= 30:
                raise HTTPException(429, '임시 사진이 많아요. 작성 중인 글을 먼저 완료해주세요.')
            cursor.execute('INSERT INTO media(user_id,data) VALUES(%s,%s)', (user_id, encoded,))
            conn.commit()
            image_id = cursor.lastrowid
    return {'id': image_id}


@router.get('/media/{image_id}')
def media(image_id: int, reveal: bool = False, user=Depends(optional_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = 0
            if user: user_id = db_user_id(cursor, user)
            cursor.execute('SELECT * FROM media WHERE media_id=%s', (image_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(404, '사진을 찾을 수 없어요.')
            if row['post_id']:
                if hidden_for(cursor, get_post(cursor, row['post_id']), user_id, reveal):
                    raise HTTPException(403, '스포일러 가림을 해제한 뒤 볼 수 있어요.')
            elif not user or row['user_id'] != user_id:
                raise HTTPException(404, '사진을 찾을 수 없어요.')
            return Response(bytes(row['data']), media_type='image/jpeg', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post('/posts', dependencies=[Depends(check_origin)])
def create_post(payload: PostInput, user=Depends(current_user)):
    body, quote = payload.body.strip(), payload.quote.strip()
    if _REVIEW_REF_PREFIX in payload.body:
        raise HTTPException(422, '글 내용에 사용할 수 없는 문자가 있어요.')
    if not body and not payload.attachReview:
        raise HTTPException(422, '글 내용을 입력해주세요.')
    if payload.attachReview and (not payload.book or payload.kind == 'line'):
        raise HTTPException(422, '한줄평을 연결할 책을 선택해주세요.')
    if payload.kind in ('quote', 'line') and not payload.book:
        raise HTTPException(422, '연결할 책을 선택해주세요.')
    if payload.kind == 'quote' and len(body) > 1000:
        raise HTTPException(422, '책 연결 글은 내 생각을 1000자 이내로 적어주세요.')
    if payload.kind == 'line' and (len(body) > 200 or payload.recommended is None):
        raise HTTPException(422, '한줄평은 200자 이내로 적고 추천 여부를 선택해주세요.')
    if payload.kind == 'line' and (payload.rating is not None or payload.images or payload.poll or quote):
        raise HTTPException(422, '한줄평에는 한줄평과 추천 여부만 남길 수 있어요.')
    options = [option.strip() for option in payload.poll]
    if options and (len(options) < 2 or any(not option or len(option) > 100 for option in options) or len(set(options)) != len(options)):
        raise HTTPException(422, '투표 항목은 서로 다른 2~6개로 입력해주세요.')
    title = payload.title.strip() or (payload.book.title if payload.book else '')
    if not title:
        raise HTTPException(422, '제목을 입력해주세요.')
    try:
        with database() as conn:
            with conn.cursor() as cursor:
                user_id = db_user_id(cursor, user)
                book_isbn = None
                if payload.book:
                    book_isbn = add_to_db(payload.book.isbn)
                    if book_isbn is None:
                        raise HTTPException(404, "저장할 책을 찾지 못했어요.")
                if payload.attachReview:
                    cursor.execute(
                        "SELECT review_id, content FROM book_review WHERE user_id=%s AND isbn=%s",
                        (user_id, book_isbn),
                    )
                    review = cursor.fetchone()
                    if not review or not (review['content'] or '').strip():
                        raise HTTPException(422, '이 책에 연결할 내 한줄평이 없어요.')
                    body = attach_review_reference(review['review_id'], body)

                category_id = get_post_category_id(cursor, 'share' if payload.kind == 'quote' else payload.category)
                post_type_id = get_post_type_id(cursor, payload.kind)
                cursor.execute("""INSERT INTO community_post (user_id, category_id, post_type_id, title, content, has_spoiler, anonymous)
                                  VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                               (user_id, category_id, post_type_id, title, body,
                                payload.hasSpoiler and payload.kind != 'line', payload.anonymous))
                post_id = cursor.lastrowid

                if book_isbn:
                    verdict = None
                    if payload.recommended is not None:
                        verdict = 'RECOMMEND' if payload.recommended else 'NOT_RECOMMEND'
                    cursor.execute("""INSERT INTO post_extra (post_id, isbn, quote, spoiler_stage, rating, recommend_verdict)
                                      VALUES (%s, %s, %s, %s, %s, %s)""",
                                   (post_id, book_isbn, quote, payload.stage.name, payload.rating, verdict))
                for image_id in set(payload.images):
                    cursor.execute('UPDATE media SET post_id=%s WHERE media_id=%s AND user_id=%s AND post_id IS NULL', (post_id, image_id, user_id))
                    changed = cursor.rowcount
                    if not changed:
                        raise HTTPException(422, '첨부할 사진을 다시 확인해주세요.')
                if options:
                    cursor.execute("""INSERT INTO polls(post_id) VALUES (%s)""", (post_id,))
                    poll_id = cursor.lastrowid
                    for position, label in enumerate(options):
                        cursor.execute("""INSERT INTO poll_options (poll_id, label, position)
                                          VALUES (%s, %s, %s)""", (poll_id, label, position))

                conn.commit()

                return {'post': serialize_post(cursor, get_post(cursor, post_id), user_id)}
    except IntegrityError as exc:
        raise HTTPException(409, '이 책에 이미 한줄평을 남겼어요. 내 활동에서 기존 한줄평을 확인해주세요.') from exc


def taste_neighbors(conn, user):
    """내가 높게 평가한 책과 같은 책·줄거리나 장르가 비슷한 책을 높게 평가한 독자 (계산은 routers/personal.py)"""
    if not user:
        return {}
    with conn.cursor() as cursor:
        user_id = db_user_id(cursor, user)
    try:
        from routers.personal import similar_readers  # 임베딩 모델이 무거워서 쓸 때 로딩
        return similar_readers(user_id)
    except (Exception, SystemExit) as exc:
        raise HTTPException(503, '취향이 비슷한 독자를 찾지 못했어요. 도서 DB와 AI 설정을 확인해주세요.') from exc


@router.get('/random-lines')
def random_lines(response: Response):
    """Sample public one-line reviews from the current review sources."""
    response.headers['Cache-Control'] = 'no-store'
    try:
        with database() as conn:
            with conn.cursor() as cursor:
                return {'lines': fetch_lines(cursor, random_limit=5)}
    except Exception as exc:
        logging.getLogger('uvicorn.error').exception('Could not load random one-line reviews')
        raise HTTPException(503, '한줄평을 불러오지 못했어요. 잠시 후 다시 시도해주세요.') from exc


@router.get('/posts')
def feed(category: Literal['all', 'talk', 'share', 'info'] = 'all', kind: Literal['all', 'free', 'quote', 'line', 'rating'] = 'all',
         mode: Literal['all', 'neighbors'] = 'all', sort: Literal['recent', 'recommended'] = 'recent',
         isbn: str | None = None, author: str | None = None, q: str = Query(default='', max_length=200),
         page: int = Query(default=1, ge=1), user=Depends(optional_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            clauses, args = [], []
            if category != 'all':
                clauses.append("pc.name = %s AND pt.name = 'free'")
                args.append(category)
            if kind == 'all':
                clauses.append("pt.name <> 'line'")
            if kind == 'rating':
                clauses.append('e.rating IS NOT NULL')
            elif kind != 'all':
                clauses.append('pt.name = %s')
                args.append(kind)
            if isbn:
                clauses.append('e.isbn = %s')
                args.append(isbn)
            if q.strip():
                clauses.append('p.title LIKE %s')
                args.append('%' + q.strip() + '%')
            if author:
                clauses.append('p.user_id = (SELECT user_id FROM users WHERE public_id = %s) AND p.anonymous = 0')
                args.append(author)
            if mode != 'all' and not user:
                return {'posts': [], 'total': 0, 'total_pages': 0, 'page': 1, 'neighbors': []}

            neighbors = taste_neighbors(conn, user) if mode == 'neighbors' else {}
            if mode == 'neighbors':
                if not neighbors:
                    return {'posts': [], 'total': 0, 'total_pages': 0, 'page': 1, 'neighbors': []}
                clauses.append('p.anonymous = 0 AND p.user_id IN (' + ','.join('%s' for _ in neighbors) + ')')
                args.extend(neighbors.keys())

            where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
            order = 'votes DESC, p.created_at DESC, p.post_id DESC' if sort == 'recommended' else 'p.created_at DESC, p.post_id DESC'
            sql = """SELECT p.*, e.isbn, e.quote, e.spoiler_stage, e.spoiler_stage AS stage, e.rating, e.recommend_verdict,
                             pt.name AS kind, pc.name AS category,
                             (SELECT COUNT(*) FROM post_like AS pl WHERE pl.post_id = p.post_id) AS votes
                       FROM community_post AS p
                       LEFT JOIN post_extra AS e ON e.post_id = p.post_id
                       LEFT JOIN post_type AS pt ON pt.type_id = p.post_type_id
                       LEFT JOIN post_category AS pc ON pc.category_id = p.category_id
                       """ + where + ' ORDER BY ' + order
            cursor.execute(sql, args)
            rows = cursor.fetchall()
            if mode == 'neighbors':
                rows = sorted(rows, key=lambda post: -neighbors[post['user_id']]['score'])
            total = len(rows)
            pages = (total + 9) // 10
            current = min(page, max(1, pages)) if total else 1
            selected = rows[(current - 1) * 10:current * 10]
            viewer_id = db_user_id(cursor, user) if user else None
            posts = [serialize_post(cursor, row, viewer_id) for row in selected]
            for post, row in zip(posts, selected):
                if mode == 'neighbors':
                    post['tasteMatch'] = {k: v for k, v in neighbors[row['user_id']].items() if k != 'score'}
            return {'posts': posts, 'total': total, 'total_pages': pages, 'page': current, 'neighbors': list(neighbors.keys()) if mode == 'neighbors' else []}


@router.get('/posts/{post_id}')
def detail(post_id: str, reveal: bool = False, user=Depends(optional_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            post = get_post(cursor, post_id)
            user_id = 0
            if user: user_id = db_user_id(cursor, user)
            result = serialize_post(cursor, post, user_id if user else None, reveal)
            comments = []
            if not result['spoilerHidden']:
                cursor.execute('SELECT * FROM post_comment WHERE post_id=%s ORDER BY created_at,comment_id', (post_id,))
                sqlresult = cursor.fetchall()
                for row in sqlresult:
                    comments.append({'id': row['comment_id'], 'parentId': row['parent_comment_id'], 'body': '삭제된 댓글입니다.' if row['deleted'] else row['content'],
                                    'author': None if row['deleted'] else author_json(
                                        cursor, row['user_id'], post['isbn'], bool(row['anonymous']), post_id=row['post_id']),
                                    'own': bool(user and row['user_id'] == user_id), 'deleted': bool(row['deleted']), 'createdAt': row['created_at']})
            return {'post': result, 'comments': comments}


@router.delete('/posts/{post_id}', dependencies=[Depends(check_origin)])
def delete_post(post_id: str, user=Depends(current_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute(
                "DELETE FROM community_post WHERE post_id = %s AND user_id = %s",
                (post_id, user_id),
            )
            if not cursor.rowcount:
                cursor.execute("SELECT 1 FROM community_post WHERE post_id = %s", (post_id,))
                if cursor.fetchone():
                    raise HTTPException(403, '내 글만 삭제할 수 있어요.')
                raise HTTPException(404, '게시물을 찾을 수 없어요.')
            conn.commit()

        return {'ok': True}


@router.post('/posts/{post_id}/recommend', dependencies=[Depends(check_origin)])
def recommend_post(post_id: str, user=Depends(current_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            # Serialize concurrent toggles and coordinate with deletion of the post.
            cursor.execute('SELECT post_id FROM community_post WHERE post_id=%s FOR UPDATE', (post_id,))
            if not cursor.fetchone():
                raise HTTPException(404, '게시글을 찾을 수 없어요.')
            post = get_post(cursor, post_id)
            if post['kind'] == 'line':
                raise HTTPException(422, '한줄평은 도서 추천 여부로만 표시해요.')
            cursor.execute('SELECT 1 FROM post_like WHERE post_id=%s AND user_id=%s', (post_id, user_id))
            existing = cursor.fetchone()
            if existing: cursor.execute('DELETE FROM post_like WHERE post_id=%s AND user_id=%s', (post_id, user_id))
            else: cursor.execute('INSERT INTO post_like (post_id, user_id) VALUES(%s,%s)', (post_id, user_id,))
            conn.commit()
            return {'post': serialize_post(cursor, get_post(cursor, post_id), user_id)}


@router.post('/posts/{post_id}/comments', dependencies=[Depends(check_origin)])
def comment(post_id: str, payload: CommentInput, user=Depends(current_user)):
    body = payload.body.strip()
    if not body: raise HTTPException(422, '댓글 내용을 입력해주세요.')
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            post = get_post(cursor, post_id)
            if payload.parentId:
                cursor.execute('SELECT comment_id, parent_comment_id FROM post_comment WHERE comment_id=%s AND post_id=%s', (payload.parentId, post_id))
                parent = cursor.fetchone()
                if parent is None: raise HTTPException(422, '답글을 연결할 댓글을 확인해주세요.')
            anonymous = bool(payload.anonymous or (post['anonymous'] and post['user_id'] == user_id))
            cursor.execute("""INSERT INTO post_comment (post_id,user_id,parent_comment_id,content,anonymous)
                           VALUES(%s,%s,%s,%s,%s)""",
                        (post_id, user_id, payload.parentId, body, int(anonymous)))
            conn.commit()
        return {'ok': True}


@router.delete('/comments/{comment_id}', dependencies=[Depends(check_origin)])
def delete_comment(comment_id: str, user=Depends(current_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute('SELECT * FROM post_comment WHERE comment_id=%s', (comment_id,))
            row = cursor.fetchone()
            if not row: raise HTTPException(404, '댓글을 찾을 수 없어요.')
            if row['user_id'] != user_id: raise HTTPException(403, '내 댓글만 삭제할 수 있어요.')
            cursor.execute("UPDATE post_comment SET content='',deleted=1 WHERE comment_id=%s", (comment_id,))
            conn.commit()
        return {'ok': True}


@router.post('/posts/{post_id}/vote', dependencies=[Depends(check_origin)])
def vote(post_id: str, payload: VoteInput, user=Depends(current_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            get_post(cursor, post_id)
            cursor.execute("""SELECT p.poll_id
                              FROM polls AS p
                              JOIN poll_options AS o ON o.poll_id = p.poll_id
                              WHERE p.post_id = %s AND o.option_id = %s""",
                           (post_id, payload.optionId))
            poll = cursor.fetchone()
            if not poll:
                raise HTTPException(422, '투표 항목을 확인해주세요.')
            cursor.execute('DELETE FROM poll_votes WHERE poll_id = %s AND user_id = %s',
                           (poll['poll_id'], user_id))
            cursor.execute("""INSERT INTO poll_votes (poll_id, user_id, option_id)
                              VALUES (%s, %s, %s)""",
                           (poll['poll_id'], user_id, payload.optionId))
            conn.commit()
            return {'ok': True}


@router.get('/profiles/{public_id}')
def public_profile(public_id: str, user=Depends(optional_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user) if user else 0
            cursor.execute('SELECT * FROM users WHERE public_id=%s AND onboarded=1', (public_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(404, '프로필을 찾을 수 없어요.')
            cursor.execute("""SELECT COUNT(*) AS total_posts,
                                     COALESCE(SUM(pt.name = 'line'), 0) AS number_of_lines
                              FROM community_post AS p
                              JOIN post_type AS pt ON pt.type_id = p.post_type_id
                              WHERE p.user_id = %s AND p.anonymous = 0""", (row['user_id'],))
            post_stats = cursor.fetchone()
            if not post_stats:
                raise HTTPException(404, 'could not fetch post stats')
            cursor.execute("""SELECT COUNT(*) AS comments
                              FROM post_comment
                              WHERE user_id = %s AND deleted = 0 AND anonymous = 0""",
                           (row['user_id'],))
            comment_stats = cursor.fetchone()
            if not comment_stats:
                raise HTTPException(404, 'could not fetch comment stats')
            legacy_lines = int(post_stats['number_of_lines'])
            lines = len(fetch_lines(cursor, user_id=row['user_id'], public_only=True))
            return {
                'profile': {'profileId': row['public_id'], 'nickname': row['nickname'], 'bio': row['about_me']},
                'own': user_id == row['user_id'],
                'stats': {
                    'library': fetch_library_stats(cursor, row['user_id']),
                    'community': {
                        'posts': int(post_stats['total_posts']) - legacy_lines,
                        'comments': int(comment_stats['comments']),
                        'lines': lines,
                    },
                },
            }


@router.get('/me/activity')
def my_activity(user=Depends(current_user)):
    conn = database()
    try:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            cursor.execute("""SELECT p.*, e.isbn, e.quote, e.spoiler_stage, e.spoiler_stage AS stage, e.rating, e.recommend_verdict,
                                     pt.name AS kind, pc.name AS category
                              FROM community_post AS p
                              LEFT JOIN post_extra AS e ON e.post_id = p.post_id
                              LEFT JOIN post_type AS pt ON pt.type_id = p.post_type_id
                              LEFT JOIN post_category AS pc ON pc.category_id = p.category_id
                              WHERE p.user_id = %s
                              ORDER BY p.created_at DESC, p.post_id DESC""", (user_id,))
            post_rows = cursor.fetchall()

            cursor.execute("""SELECT c.comment_id AS id, c.post_id, c.content AS body,
                                     c.created_at, p.title
                              FROM post_comment AS c
                              JOIN community_post AS p ON p.post_id = c.post_id
                              WHERE c.user_id = %s AND c.deleted = 0
                              ORDER BY c.created_at DESC, c.comment_id DESC""", (user_id,))
            comment_rows = cursor.fetchall()

            posts = [serialize_post(cursor, row, user_id) for row in post_rows]
            comments = [
                {
                    'id': row['id'],
                    'post_id': row['post_id'],
                    'title': row['title'],
                    'body': row['body'],
                    'created_at': row['created_at'],
                }
                for row in comment_rows
            ]
            lines = fetch_lines(cursor, user_id=user_id)
            events = [row['created_at'] for row in post_rows + comment_rows] + [line['createdAt'] for line in lines]
            days = set()
            for value in events:
                if isinstance(value, datetime):
                    days.add(value.date().isoformat())
                elif isinstance(value, (int, float)):
                    days.add(datetime.fromtimestamp(value / 1000, KOREA).date().isoformat())

            legacy_lines = sum(post['kind'] == 'line' for post in posts)
            return {
                'posts': posts,
                'comments': comments,
                'lines': lines,
                'counts': {
                    'posts': len(posts) - legacy_lines,
                    'comments': len(comments),
                    'lines': len(lines),
                },
                'activityDays': sorted(days),
            }
    finally:
        conn.close()


@router.get('/books/{isbn}/lines')
def book_lines(isbn: str, response: Response):
    if not re.fullmatch(ISBN, isbn):
        raise HTTPException(422, 'ISBN 정보를 확인해주세요.')
    response.headers['Cache-Control'] = 'no-store'
    with database() as conn:
        with conn.cursor() as cursor:
            return {'lines': fetch_lines(cursor, isbn=isbn)}


@router.get('/books/{isbn}/summary')
def book_summary(isbn: str):
    with database() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""SELECT
                           COUNT(*) AS total,
                           AVG(e.rating) AS average,
                           COUNT(e.rating) AS ratings,
                           SUM(CASE WHEN pt.name='line' AND e.recommend_verdict='RECOMMEND' THEN 1 ELSE 0 END) AS yes,
                           SUM(CASE WHEN pt.name='line' THEN 1 ELSE 0 END) AS number_of_lines
                           FROM community_post AS p
                           LEFT JOIN post_type AS pt ON p.post_type_id = pt.type_id
                           LEFT JOIN post_extra AS e ON p.post_id = e.post_id
                           WHERE e.isbn=%s""", (isbn,))
            row = cursor.fetchone()
            if not row:
                return
            lines = fetch_lines(cursor, isbn=isbn)
            cursor.execute('SELECT AVG(rating) AS average, COUNT(*) AS ratings FROM book_review WHERE isbn=%s', (isbn,))
            review_summary = cursor.fetchone()
            ratings = int(row['ratings'] or 0) + int(review_summary['ratings'] or 0)
            rating_sum = float(row['average'] or 0) * int(row['ratings'] or 0) + float(review_summary['average'] or 0) * int(review_summary['ratings'] or 0)
            return {
                'total': row['total'],
                'averageRating': round(rating_sum / ratings, 1) if ratings else None,
                'ratingCount': ratings,
                'recommended': sum(line['recommended'] is True for line in lines),
                'lineCount': len(lines),
            }


@router.get('/recommendations')
def genre_recommendations(user=Depends(current_user)):
    with database() as conn:
        with conn.cursor() as cursor:
            user_id = db_user_id(cursor, user)
            genre_prefs = fetch_genre_preferences(cursor, user_id)
            liked = genre_prefs["likedGenres"]
            disliked = genre_prefs["dislikedGenres"]
    try:
        from routers.personal import recommendations_for  # 임베딩 모델이 무거워서 쓸 때 로딩
        return recommendations_for(user, liked, disliked)
    except HTTPException:
        raise
    except (Exception, SystemExit) as exc:
        raise HTTPException(503, '취향 도서를 불러오지 못했어요. 도서 DB와 AI 설정을 확인해주세요.') from exc
