"""Authenticated community APIs. No writes to the existing MySQL database."""
import base64
import binascii
import io
import json
import re
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from routers.auth import current_user, check_origin
from routers.community_store import database, now, key, ensure_profile, profile_json, author_json

router = APIRouter(prefix='/api/community', tags=['community'])
KOREA = timezone(timedelta(hours=9))
ISBN = r'^(978|979)\d{10}$'


def optional_user(request: Request):
    try:
        return current_user(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise


def require_ready(conn, user):
    profile = ensure_profile(conn, user)
    if not profile['onboarded']:
        raise HTTPException(409, '먼저 닉네임과 취향 설정을 완료해주세요.')
    return profile


class ProfileUpdate(BaseModel):
    nickname: str = Field(min_length=2, max_length=20)
    bio: str = Field(default='', max_length=200)
    likedGenres: list[str] = Field(default_factory=list, max_length=40)
    dislikedGenres: list[str] = Field(default_factory=list, max_length=40)
    onboarded: bool = True


class Book(BaseModel):
    isbn: str = Field(pattern=ISBN)
    title: str = Field(min_length=1, max_length=255)
    author: str = Field(default='', max_length=255)
    cover_image_url: str | None = Field(default=None, max_length=1000)
    genres: list[str] = Field(default_factory=list, max_length=40)


class PostInput(BaseModel):
    kind: Literal['free', 'quote', 'line'] = 'quote'
    category: Literal['talk', 'share', 'info'] = 'share'
    title: str = Field(default='', max_length=120)
    body: str = Field(min_length=1, max_length=3000)
    quote: str = Field(default='', max_length=300)
    book: Book | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    recommended: bool | None = None
    stage: int = Field(default=0, ge=0, le=2)
    hasSpoiler: bool = False
    anonymous: bool = False
    images: list[str] = Field(default_factory=list, max_length=3)
    poll: list[str] = Field(default_factory=list, max_length=6)


class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    parentId: str | None = Field(default=None, max_length=64)
    anonymous: bool = False


class VoteInput(BaseModel):
    optionId: str = Field(min_length=1, max_length=64)


class ImageInput(BaseModel):
    data: str = Field(min_length=1, max_length=4300000)


class ReadingItem(BaseModel):
    book: Book
    rating: int = Field(default=0, ge=0, le=5)
    status: Literal['WISH', 'READING', 'COMPLETED'] = 'WISH'


class ReadingSync(BaseModel):
    records: list[ReadingItem] = Field(max_length=3000)


class ProgressInput(BaseModel):
    progress: int = Field(ge=0, le=2)


def words(values):
    result = []
    for value in values:
        value = value.strip()
        if not value or len(value) > 30:
            raise HTTPException(422, '장르는 1~30자로 입력해주세요.')
        if value not in result:
            result.append(value)
    return result


def get_post(conn, post_id):
    post = conn.execute('SELECT * FROM posts WHERE id=?', (post_id,)).fetchone()
    if not post:
        raise HTTPException(404, '게시물을 찾을 수 없어요.')
    return post


def progress_for(conn, user, isbn):
    if not user or not isbn:
        return 0
    row = conn.execute('SELECT progress,status FROM reading WHERE owner=? AND isbn=?', (user['id'], isbn)).fetchone()
    return 2 if row and row['status'] == 'COMPLETED' else row['progress'] if row else 0


def hidden_for(conn, post, user, reveal=False):
    if reveal or (user and user['id'] == post['owner']):
        return False
    return bool(post['has_spoiler'] or (post['isbn'] and post['stage'] > progress_for(conn, user, post['isbn'])))


def serialize_post(conn, post, user=None, reveal=False):
    own = bool(user and user['id'] == post['owner'])
    hidden = hidden_for(conn, post, user, reveal)
    post_id = post['id']
    count = conn.execute('SELECT COUNT(*) FROM endorsements WHERE post_id=?', (post_id,)).fetchone()[0]
    comment_count = conn.execute('SELECT COUNT(*) FROM comments WHERE post_id=? AND deleted=0', (post_id,)).fetchone()[0]
    endorsed = bool(user and conn.execute('SELECT 1 FROM endorsements WHERE post_id=? AND owner=?', (post_id, user['id'])).fetchone())
    poll = None
    if not hidden:
        options = conn.execute('SELECT p.id,p.label,(SELECT COUNT(*) FROM votes v WHERE v.option_id=p.id) AS votes FROM polls p WHERE p.post_id=? ORDER BY position', (post_id,)).fetchall()
        if options:
            vote = conn.execute('SELECT option_id FROM votes WHERE post_id=? AND owner=?', (post_id, user['id'])).fetchone() if user else None
            poll = {'options': [dict(o) for o in options], 'total': sum(o['votes'] for o in options), 'myVote': vote['option_id'] if vote else None}
    return {'id': post_id, 'kind': post['kind'], 'category': post['category'],
            'title': '스포일러가 포함된 글' if hidden else post['title'],
            'body': None if hidden else post['body'], 'quote': None if hidden else post['quote'],
            'book': json.loads(post['book']) if post['book'] else None,
            'rating': None if hidden else post['rating'], 'recommended': None if hidden or post['recommended'] is None else bool(post['recommended']),
            'stage': post['stage'], 'hasSpoiler': bool(post['has_spoiler']), 'spoilerHidden': hidden, 'author': author_json(conn, post['owner'], post['isbn'], bool(post['anonymous'])),
            'own': own, 'createdAt': post['created_at'], 'recommendCount': count, 'recommendedByMe': endorsed,
            'commentCount': comment_count, 'images': [] if hidden else [dict(row) for row in conn.execute('SELECT id FROM media WHERE post_id=? ORDER BY created_at,id', (post_id,))],
            'poll': poll}


@router.get('/me')
def me(user=Depends(current_user)):
    with database() as conn:
        return {'profile': profile_json(ensure_profile(conn, user))}


@router.put('/me', dependencies=[Depends(check_origin)])
def update_me(payload: ProfileUpdate, user=Depends(current_user)):
    nickname = payload.nickname.strip()
    if len(nickname) < 2 or any(ord(c) < 32 for c in nickname):
        raise HTTPException(422, '닉네임은 2~20자로 입력해주세요.')
    liked, disliked = words(payload.likedGenres), words(payload.dislikedGenres)
    if set(liked) & set(disliked):
        raise HTTPException(422, '같은 장르를 선호·비선호에 동시에 선택할 수 없어요.')
    try:
        with database() as conn:
            ensure_profile(conn, user)
            conn.execute('UPDATE profiles SET nickname=?,nickname_key=?,bio=?,liked=?,disliked=?,onboarded=? WHERE owner=?',
                         (nickname, key(nickname), payload.bio.strip(), json.dumps(liked, ensure_ascii=False), json.dumps(disliked, ensure_ascii=False), int(payload.onboarded), user['id']))
            return {'profile': profile_json(ensure_profile(conn, user))}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, '이미 사용 중인 닉네임이에요.') from exc


@router.post('/reading-sync', dependencies=[Depends(check_origin)])
def reading_sync(payload: ReadingSync, user=Depends(current_user)):
    with database() as conn:
        ensure_profile(conn, user)
        incoming = set()
        for item in payload.records:
            isbn = item.book.isbn
            incoming.add(isbn)
            conn.execute('''INSERT INTO reading(owner,isbn,book,rating,status,genres) VALUES(?,?,?,?,?,?)
                            ON CONFLICT(owner,isbn) DO UPDATE SET book=excluded.book,rating=excluded.rating,status=excluded.status,genres=excluded.genres''',
                         (user['id'], isbn, item.book.model_dump_json(), item.rating, item.status, json.dumps(item.book.genres, ensure_ascii=False)))
        for row in conn.execute('SELECT isbn FROM reading WHERE owner=?', (user['id'],)).fetchall():
            if row['isbn'] not in incoming:
                conn.execute('DELETE FROM reading WHERE owner=? AND isbn=?', (user['id'], row['isbn']))
        return {'progress': {row['isbn']: 2 if row['status'] == 'COMPLETED' else row['progress'] for row in conn.execute('SELECT * FROM reading WHERE owner=?', (user['id'],))}}


@router.put('/progress/{isbn}', dependencies=[Depends(check_origin)])
def update_progress(isbn: str, payload: ProgressInput, user=Depends(current_user)):
    with database() as conn:
        changed = conn.execute('UPDATE reading SET progress=? WHERE owner=? AND isbn=?', (payload.progress, user['id'], isbn))
        if not changed.rowcount:
            raise HTTPException(404, '서재를 먼저 불러온 뒤 진도를 설정해주세요.')
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
    image_id = secrets.token_hex(16)
    with database() as conn:
        require_ready(conn, user)
        # Unattached uploads are private and removed after a day.
        conn.execute('DELETE FROM media WHERE post_id IS NULL AND created_at<?', (now() - 86400000,))
        count = conn.execute('SELECT COUNT(*) FROM media WHERE owner=? AND post_id IS NULL', (user['id'],)).fetchone()[0]
        if count >= 30:
            raise HTTPException(429, '임시 사진이 많아요. 작성 중인 글을 먼저 완료해주세요.')
        conn.execute('INSERT INTO media(id,owner,data,created_at) VALUES(?,?,?,?)', (image_id, user['id'], encoded, now()))
    return {'id': image_id}


@router.get('/media/{image_id}')
def media(image_id: str, reveal: bool = False, user=Depends(optional_user)):
    with database() as conn:
        row = conn.execute('SELECT * FROM media WHERE id=?', (image_id,)).fetchone()
        if not row:
            raise HTTPException(404, '사진을 찾을 수 없어요.')
        if row['post_id']:
            if hidden_for(conn, get_post(conn, row['post_id']), user, reveal):
                raise HTTPException(403, '스포일러 가림을 해제한 뒤 볼 수 있어요.')
        elif not user or row['owner'] != user['id']:
            raise HTTPException(404, '사진을 찾을 수 없어요.')
        return Response(bytes(row['data']), media_type='image/jpeg', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})


@router.post('/posts', dependencies=[Depends(check_origin)])
def create_post(payload: PostInput, user=Depends(current_user)):
    body, quote = payload.body.strip(), payload.quote.strip()
    if not body:
        raise HTTPException(422, '글 내용을 입력해주세요.')
    if payload.kind in ('quote', 'line') and not payload.book:
        raise HTTPException(422, '연결할 책을 선택해주세요.')
    if payload.kind == 'quote' and not quote:
        raise HTTPException(422, '인상 깊은 문장을 입력해주세요.')
    if payload.kind == 'quote' and len(body) > 1000:
        raise HTTPException(422, '책 연결 글은 내 생각을 1000자 이내로 적어주세요.')
    if payload.kind == 'line' and (len(body) > 200 or payload.recommended is None):
        raise HTTPException(422, '한줄평은 200자 이내로 적고 추천 여부를 선택해주세요.')
    if payload.kind == 'line' and (payload.rating is not None or payload.images or payload.poll or quote):
        raise HTTPException(422, '한줄평에는 한줄평과 추천 여부만 남길 수 있어요.')
    if payload.anonymous and not payload.book:
        raise HTTPException(422, '익명 가명은 책이 연결된 글에서 사용할 수 있어요.')
    options = [option.strip() for option in payload.poll]
    if options and (len(options) < 2 or any(not option or len(option) > 100 for option in options) or len(set(options)) != len(options)):
        raise HTTPException(422, '투표 항목은 서로 다른 2~6개로 입력해주세요.')
    post_id = secrets.token_hex(16)
    title = payload.title.strip() or (payload.book.title if payload.book else '')
    if not title:
        raise HTTPException(422, '제목을 입력해주세요.')
    try:
        with database() as conn:
            require_ready(conn, user)
            conn.execute('''INSERT INTO posts(id,owner,kind,category,title,body,quote,isbn,book,rating,recommended,stage,anonymous,has_spoiler,created_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                         (post_id, user['id'], payload.kind, payload.category, title, body, quote,
                          payload.book.isbn if payload.book else None, payload.book.model_dump_json() if payload.book else None,
                          payload.rating, None if payload.recommended is None else int(payload.recommended), payload.stage, int(payload.anonymous), int(payload.hasSpoiler), now()))
            for image_id in set(payload.images):
                changed = conn.execute('UPDATE media SET post_id=? WHERE id=? AND owner=? AND post_id IS NULL', (post_id, image_id, user['id']))
                if not changed.rowcount:
                    raise HTTPException(422, '첨부할 사진을 다시 확인해주세요.')
            for position, label in enumerate(options):
                conn.execute('INSERT INTO polls(id,post_id,label,position) VALUES(?,?,?,?)', (secrets.token_hex(16), post_id, label, position))
            return {'post': serialize_post(conn, get_post(conn, post_id), user)}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, '이 책에 이미 한줄평을 남겼어요. 내 활동에서 기존 한줄평을 확인해주세요.') from exc


def taste_neighbors(conn, user):
    if not user:
        return {}
    own = ensure_profile(conn, user)
    liked, disliked = set(json.loads(own['liked'])), set(json.loads(own['disliked']))
    ratings = {r['isbn']: r['rating'] for r in conn.execute('SELECT isbn,rating FROM reading WHERE owner=? AND rating>0', (user['id'],))}
    neighbors = {}
    for profile in conn.execute('SELECT * FROM profiles WHERE owner!=? AND onboarded=1', (user['id'],)):
        other_liked = set(json.loads(profile['liked']))
        union = liked | other_liked
        genre_score = len(liked & other_liked) / len(union) if union else 0
        others = {r['isbn']: r['rating'] for r in conn.execute('SELECT isbn,rating FROM reading WHERE owner=? AND rating>0', (profile['owner'],))}
        common = ratings.keys() & others.keys()
        rating_score = sum(1 - abs(ratings[isbn] - others[isbn]) / 4 for isbn in common) / len(common) if common else 0
        if not common and not (liked & other_liked):
            continue
        score = .6 * rating_score + .4 * genre_score - .3 * (len(disliked & other_liked) / max(1, len(other_liked)))
        if score > 0:
            neighbors[profile['owner']] = {'score': round(score, 3), 'sharedBooks': len(common), 'sharedGenres': sorted(liked & other_liked)}
    return neighbors


@router.get('/posts')
def feed(category: Literal['all', 'talk', 'share', 'info'] = 'all', kind: Literal['all', 'free', 'quote', 'line', 'rating'] = 'all',
         mode: Literal['all', 'following', 'neighbors'] = 'all', sort: Literal['recent', 'recommended'] = 'recent',
         isbn: str | None = None, author: str | None = None, q: str = Query(default='', max_length=200),
         page: int = Query(default=1, ge=1), user=Depends(optional_user)):
    with database() as conn:
        clauses, args = [], []
        if category != 'all': clauses.append('p.category=?'); args.append(category)
        if kind == 'rating': clauses.append('p.rating IS NOT NULL')
        elif kind != 'all': clauses.append('p.kind=?'); args.append(kind)
        if isbn: clauses.append('p.isbn=?'); args.append(isbn)
        if q.strip(): clauses.append('json_extract(p.book,\'$.title\') LIKE ?'); args.append('%' + q.strip() + '%')
        if author:
            clauses.append('p.owner=(SELECT owner FROM profiles WHERE public_id=?) AND p.anonymous=0'); args.append(author)
        if mode != 'all' and not user:
            return {'posts': [], 'total': 0, 'total_pages': 0, 'page': 1, 'neighbors': []}
        neighbors = taste_neighbors(conn, user) if mode == 'neighbors' else {}
        if mode == 'following':
            clauses.append('p.anonymous=0 AND p.owner IN (SELECT target FROM follows WHERE follower=?)'); args.append(user['id'])
        if mode == 'neighbors':
            if not neighbors:
                return {'posts': [], 'total': 0, 'total_pages': 0, 'page': 1, 'neighbors': []}
            clauses.append('p.anonymous=0 AND p.owner IN (' + ','.join('?' for _ in neighbors) + ')'); args.extend(neighbors)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        order = 'votes DESC,p.created_at DESC,p.id DESC' if sort == 'recommended' else 'p.created_at DESC,p.id DESC'
        sql = 'SELECT p.*,(SELECT COUNT(*) FROM endorsements e WHERE e.post_id=p.id) AS votes FROM posts p' + where + ' ORDER BY ' + order
        rows = conn.execute(sql, args).fetchall()
        if mode == 'neighbors':
            # Keep selected sort within each similarity score; never expose author IDs.
            rows = sorted(rows, key=lambda p: -neighbors[p['owner']]['score'])
        total = len(rows); pages = (total + 9) // 10; current = min(page, max(1, pages))
        selected = rows[(current - 1) * 10:current * 10]
        posts = [serialize_post(conn, row, user) for row in selected]
        for post, row in zip(posts, selected):
            if mode == 'neighbors': post['tasteMatch'] = {k: v for k, v in neighbors[row['owner']].items() if k != 'score'}
        return {'posts': posts, 'total': total, 'total_pages': pages, 'page': current}


@router.get('/posts/{post_id}')
def detail(post_id: str, reveal: bool = False, user=Depends(optional_user)):
    with database() as conn:
        post = get_post(conn, post_id)
        result = serialize_post(conn, post, user, reveal)
        comments = []
        if not result['spoilerHidden']:
            for row in conn.execute('SELECT * FROM comments WHERE post_id=? ORDER BY created_at,id', (post_id,)):
                comments.append({'id': row['id'], 'parentId': row['parent_id'], 'body': '삭제된 댓글입니다.' if row['deleted'] else row['body'],
                                 'author': None if row['deleted'] else author_json(conn, row['owner'], post['isbn'], bool(row['anonymous'])),
                                 'own': bool(user and row['owner'] == user['id']), 'deleted': bool(row['deleted']), 'createdAt': row['created_at']})
        return {'post': result, 'comments': comments}


@router.delete('/posts/{post_id}', dependencies=[Depends(check_origin)])
def delete_post(post_id: str, user=Depends(current_user)):
    with database() as conn:
        post = get_post(conn, post_id)
        if post['owner'] != user['id']: raise HTTPException(403, '내 글만 삭제할 수 있어요.')
        # Comments have self references; remove leaf replies first.
        conn.execute('DELETE FROM comments WHERE post_id=? AND parent_id IS NOT NULL', (post_id,))
        conn.execute('DELETE FROM posts WHERE id=?', (post_id,))
    return {'ok': True}


@router.post('/posts/{post_id}/recommend', dependencies=[Depends(check_origin)])
def recommend_post(post_id: str, user=Depends(current_user)):
    with database() as conn:
        require_ready(conn, user); post = get_post(conn, post_id)
        if post['kind'] == 'line': raise HTTPException(422, '한줄평은 도서 추천 여부로만 표시해요.')
        if post['owner'] == user['id']: raise HTTPException(422, '내 글에는 추천을 누를 수 없어요.')
        existing = conn.execute('SELECT 1 FROM endorsements WHERE post_id=? AND owner=?', (post_id, user['id'])).fetchone()
        if existing: conn.execute('DELETE FROM endorsements WHERE post_id=? AND owner=?', (post_id, user['id']))
        else: conn.execute('INSERT INTO endorsements VALUES(?,?,?)', (post_id, user['id'], now()))
        return {'post': serialize_post(conn, get_post(conn, post_id), user)}


@router.post('/posts/{post_id}/comments', dependencies=[Depends(check_origin)])
def comment(post_id: str, payload: CommentInput, user=Depends(current_user)):
    body = payload.body.strip()
    if not body: raise HTTPException(422, '댓글 내용을 입력해주세요.')
    with database() as conn:
        require_ready(conn, user); post = get_post(conn, post_id)
        if payload.parentId:
            parent = conn.execute('SELECT * FROM comments WHERE id=? AND post_id=?', (payload.parentId, post_id)).fetchone()
            if not parent or parent['parent_id']: raise HTTPException(422, '대댓글을 연결할 원래 댓글을 확인해주세요.')
        anonymous = bool(payload.anonymous or (post['anonymous'] and post['owner'] == user['id']))
        if anonymous and not post['isbn']: raise HTTPException(422, '책 연결 글에서 익명 댓글을 사용할 수 있어요.')
        conn.execute('INSERT INTO comments(id,post_id,owner,parent_id,body,anonymous,created_at) VALUES(?,?,?,?,?,?,?)',
                     (secrets.token_hex(16), post_id, user['id'], payload.parentId, body, int(anonymous), now()))
    return {'ok': True}


@router.delete('/comments/{comment_id}', dependencies=[Depends(check_origin)])
def delete_comment(comment_id: str, user=Depends(current_user)):
    with database() as conn:
        row = conn.execute('SELECT * FROM comments WHERE id=?', (comment_id,)).fetchone()
        if not row: raise HTTPException(404, '댓글을 찾을 수 없어요.')
        if row['owner'] != user['id']: raise HTTPException(403, '내 댓글만 삭제할 수 있어요.')
        conn.execute("UPDATE comments SET body='',deleted=1 WHERE id=?", (comment_id,))
    return {'ok': True}


@router.post('/posts/{post_id}/vote', dependencies=[Depends(check_origin)])
def vote(post_id: str, payload: VoteInput, user=Depends(current_user)):
    with database() as conn:
        require_ready(conn, user); get_post(conn, post_id)
        if not conn.execute('SELECT 1 FROM polls WHERE id=? AND post_id=?', (payload.optionId, post_id)).fetchone():
            raise HTTPException(422, '투표 항목을 확인해주세요.')
        conn.execute('INSERT INTO votes(post_id,owner,option_id) VALUES(?,?,?) ON CONFLICT(post_id,owner) DO UPDATE SET option_id=excluded.option_id',
                     (post_id, user['id'], payload.optionId))
        return {'ok': True}


@router.get('/profiles/{public_id}')
def public_profile(public_id: str, user=Depends(optional_user)):
    with database() as conn:
        row = conn.execute('SELECT * FROM profiles WHERE public_id=? AND onboarded=1', (public_id,)).fetchone()
        if not row: raise HTTPException(404, '프로필을 찾을 수 없어요.')
        followed = bool(user and conn.execute('SELECT 1 FROM follows WHERE follower=? AND target=?', (user['id'], row['owner'])).fetchone())
        return {'profile': {'profileId': row['public_id'], 'nickname': row['nickname'], 'bio': row['bio']}, 'following': followed,
                'own': bool(user and user['id'] == row['owner'])}


@router.post('/profiles/{public_id}/follow', dependencies=[Depends(check_origin)])
def follow(public_id: str, user=Depends(current_user)):
    with database() as conn:
        require_ready(conn, user)
        row = conn.execute('SELECT owner FROM profiles WHERE public_id=? AND onboarded=1', (public_id,)).fetchone()
        if not row: raise HTTPException(404, '프로필을 찾을 수 없어요.')
        if row['owner'] == user['id']: raise HTTPException(422, '내 계정은 구독할 수 없어요.')
        existing = conn.execute('SELECT 1 FROM follows WHERE follower=? AND target=?', (user['id'], row['owner'])).fetchone()
        if existing: conn.execute('DELETE FROM follows WHERE follower=? AND target=?', (user['id'], row['owner']))
        else: conn.execute('INSERT INTO follows VALUES(?,?)', (user['id'], row['owner']))
        return {'following': not bool(existing)}


@router.get('/me/activity')
def my_activity(user=Depends(current_user)):
    with database() as conn:
        ensure_profile(conn, user)
        posts = conn.execute('SELECT * FROM posts WHERE owner=? ORDER BY created_at DESC,id DESC', (user['id'],)).fetchall()
        comments = conn.execute('SELECT c.id,c.body,c.post_id,c.created_at,p.title,p.isbn FROM comments c JOIN posts p ON p.id=c.post_id WHERE c.owner=? AND c.deleted=0 ORDER BY c.created_at DESC', (user['id'],)).fetchall()
        events = [p['created_at'] for p in posts] + [c['created_at'] for c in comments]
        days = sorted({datetime.fromtimestamp(value / 1000, KOREA).date().isoformat() for value in events})
        return {'posts': [serialize_post(conn, p, user) for p in posts], 'comments': [dict(row) for row in comments],
                'counts': {'posts': len(posts), 'comments': len(comments), 'lines': sum(p['kind'] == 'line' for p in posts)}, 'activityDays': days}


@router.get('/books/{isbn}/summary')
def book_summary(isbn: str):
    with database() as conn:
        row = conn.execute('SELECT COUNT(*) AS total,AVG(rating) AS average,COUNT(rating) AS ratings,SUM(CASE WHEN kind=\'line\' AND recommended=1 THEN 1 ELSE 0 END) AS yes,SUM(CASE WHEN kind=\'line\' THEN 1 ELSE 0 END) AS lines FROM posts WHERE isbn=?', (isbn,)).fetchone()
        return {'total': row['total'], 'averageRating': round(row['average'], 1) if row['average'] is not None else None,
                'ratingCount': row['ratings'], 'recommended': row['yes'] or 0, 'lineCount': row['lines'] or 0}


@router.get('/recommendations')
def genre_recommendations(user=Depends(current_user)):
    with database() as conn:
        profile = ensure_profile(conn, user)
        liked, disliked = json.loads(profile['liked']), json.loads(profile['disliked'])
    if not liked:
        return {'books': [], 'message': '좋아하는 장르를 고르면 책을 추천해드려요.'}
    # Match the user's genres across the catalog before sorting by overlap.
    # Keep this read-only; the teammate-owned catalog schema is unchanged.
    aliases = {'소설(일반문학)': '소설', '스릴러': '스릴러·호러', '공포·스릴러': '스릴러·호러', '고전소설': '소설',
               '경제·경영': '경제경영', '사회·정치': '사회과학', 'IT·컴퓨터': '기술과학', '과학(일반)': '자연과학', '종교학': '종교'}
    def canonical(value):
        value = str(value or '').strip()
        return aliases.get(value, value)
    good, bad = {canonical(value) for value in liked}, {canonical(value) for value in disliked}
    good.discard(''); bad.discard('')
    # Include both selected names and catalog aliases when querying candidates.
    names = sorted(good | {str(value).strip() for value in liked} | {name for name, target in aliases.items() if target in good})
    placeholders = ','.join(['%s'] * len(names))
    from common import get_mysql_connection
    try:
        connection = get_mysql_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'''SELECT b.isbn,b.title,b.author,b.publisher,b.publish_year,b.description,b.cover_image_url,b.loan_count,
                                  g.name AS genre,GROUP_CONCAT(DISTINCT sg.name SEPARATOR '|') AS subgenres
                                  FROM book b LEFT JOIN genre g ON g.genre_id=b.genre_id
                                  LEFT JOIN book_subgenre bs ON bs.isbn=b.isbn LEFT JOIN genre sg ON sg.genre_id=bs.genre_id
                                  WHERE g.name IN ({placeholders}) OR EXISTS (
                                    SELECT 1 FROM book_subgenre match_bs JOIN genre match_g ON match_g.genre_id=match_bs.genre_id
                                    WHERE match_bs.isbn=b.isbn AND match_g.name IN ({placeholders}))
                                  GROUP BY b.isbn,g.name''', tuple(names + names))
                candidates = cursor.fetchall()
        finally:
            connection.close()
    except (Exception, SystemExit) as exc:
        raise HTTPException(503, '취향 도서를 불러오지 못했어요. 도서 DB 연결을 확인해주세요.') from exc
    selected = []
    for book in candidates:
        tags = {canonical(book.get('genre'))} | {canonical(value) for value in (book.get('subgenres') or '').split('|')}
        matches = tags & good
        if matches and not tags & bad:
            # Report the user's labels, and count equivalent aliases only once.
            labels = {canonical(value): value for value in reversed(liked)}
            selected.append({**book, 'matchedGenres': [labels[tag] for tag in sorted(matches)], 'matchedGenreCount': len(matches)})
    selected.sort(key=lambda book: (-book['matchedGenreCount'], -int(book.get('loan_count') or 0), str(book.get('title') or ''), str(book['isbn'])))
    return {'books': selected[:6], 'message': None if selected else '선택한 선호 장르와 일치하는 도서가 아직 없어요. 비선호 장르가 포함된 책은 제외해요.'}
