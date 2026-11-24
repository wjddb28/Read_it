"""One public reading response, including comments saved before the UI was unified."""
import random

from routers.community_store import author_json


def fetch_lines(cursor, isbn=None, user_id=None, public_only=False, random_limit=None):
    filters, args = [], []
    if isbn is not None:
        filters.append('r.isbn=%s'); args.append(isbn)
    if user_id is not None:
        filters.append('r.user_id=%s'); args.append(user_id)
    cursor.execute("""SELECT r.review_id AS source_id, r.user_id, r.isbn, r.content, r.rating,
                             r.has_spoiler, r.created_at, b.title AS book_title, b.author AS book_author
                      FROM book_review r JOIN users u ON u.user_id=r.user_id
                      JOIN book b ON b.isbn=r.isbn
                      WHERE u.is_suspended=0 AND TRIM(COALESCE(r.content,''))<>''"""
                   + ''.join(' AND ' + f for f in filters), tuple(args))
    rows = [dict(row, source='review', anonymous=False, recommend_verdict=None, stage=None)
            for row in cursor.fetchall()]
    filters = [f.replace('r.', 'p.' if 'user_id' in f else 'e.') for f in filters]
    cursor.execute("""SELECT p.post_id AS source_id, p.user_id, e.isbn, p.content, e.rating,
                             p.has_spoiler, p.created_at, p.anonymous, e.recommend_verdict,
                             e.spoiler_stage AS stage, b.title AS book_title, b.author AS book_author
                      FROM community_post p JOIN post_type pt ON pt.type_id=p.post_type_id
                      JOIN post_extra e ON e.post_id=p.post_id
                      JOIN book b ON b.isbn=e.isbn JOIN users u ON u.user_id=p.user_id
                      WHERE pt.name='line' AND u.is_suspended=0 AND TRIM(p.content)<>''"""
                   + ''.join(' AND ' + f for f in filters), tuple(args))
    rows += [dict(row, source='post') for row in cursor.fetchall()]
    # Keep distinct old responses; show an identical public comment only once.
    seen, lines = set(), []
    for row in rows:
        if public_only and row['anonymous']:
            continue
        identity = (row['source'], row['source_id']) if row['anonymous'] else (
            row['user_id'], row['isbn'], row['content'].strip())
        if identity in seen:
            continue
        seen.add(identity)
        verdict = row['recommend_verdict']
        lines.append({
            'id': f"{row['source']}:{row['source_id']}", 'body': row['content'],
            'rating': row['rating'], 'hasSpoiler': False, 'createdAt': row['created_at'],
            'book': {'isbn': row['isbn'], 'title': row['book_title'], 'author': row['book_author']},
            'author': author_json(cursor, row['user_id'], row['isbn'], bool(row['anonymous']),
                                  post_id=row['source_id'] if row['source'] == 'post' else None),
            'recommended': True if verdict == 'RECOMMEND' else False if verdict == 'NOT_RECOMMEND' else None,
        })
    if random_limit is not None:
        return random.sample(lines, min(random_limit, len(lines)))
    return sorted(lines, key=lambda line: str(line['createdAt']), reverse=True)


# Keep the reference in the post body envelope so existing databases need no migration.
_REVIEW_REF_PREFIX = "\x1eREADIT_REVIEW:"


def split_review_reference(content):
    if not content.startswith(_REVIEW_REF_PREFIX):
        return None, content
    header, separator, body = content.partition("\n")
    identifier = header[len(_REVIEW_REF_PREFIX):]
    if not separator or not identifier.isascii() or not identifier.isdecimal() or len(identifier) > 10:
        return None, content
    return int(identifier), body


def attach_review_reference(review_id, body):
    return f"{_REVIEW_REF_PREFIX}{review_id}\n{body}"


def remove_legacy_review_copies(cursor, user_id, isbn, content, rating):
    """Clean up older posts that stored the entire imported review as their body."""
    if not content or not content.strip():
        return
    cursor.execute("""SELECT p.post_id, p.content, pt.name AS kind, e.rating
                      FROM community_post p JOIN post_type pt ON pt.type_id=p.post_type_id
                      JOIN post_extra e ON e.post_id=p.post_id
                      WHERE p.user_id=%s AND e.isbn=%s AND TRIM(p.content)=%s""",
                   (user_id, isbn, content.strip()))
    for row in cursor.fetchall():
        if row['content'].strip() != content.strip():
            continue
        if row['kind'] == 'line':
            cursor.execute('DELETE FROM community_post WHERE post_id=%s AND user_id=%s',
                           (row['post_id'], user_id))
        else:
            cursor.execute("UPDATE community_post SET content='' WHERE post_id=%s AND user_id=%s",
                           (row['post_id'], user_id))
            if row['rating'] == rating:
                cursor.execute('UPDATE post_extra SET rating=NULL WHERE post_id=%s', (row['post_id'],))
