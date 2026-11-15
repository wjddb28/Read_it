"""Helpers shared by community and profile routes."""
import hashlib
import unicodedata


def key(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


def author_json(cursor, owner, isbn=None, anonymous=False, post_id=None):
    """사용자 ID, 포스트 ID, ISBN을 종합적으로 고려해서 가짜 닉네임 생성. 가명을 사용하는 포스트에서만 생성됩니다."""
    if anonymous:
        identity = '\0'.join(map(str, (
            'community-anonymous-v1',
            owner,
            post_id or '',
            isbn or '',
        )))
        digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()
        return {'nickname': '책갈피 ' + digest[:8], 'profileId': None, 'anonymous': True}
    cursor.execute('SELECT public_id,nickname FROM users WHERE user_id=%s', (owner,))
    row = cursor.fetchone()
    return {'nickname': row['nickname'], 'profileId': row['public_id'], 'anonymous': False}
