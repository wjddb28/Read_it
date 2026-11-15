# 커뮤니티 포스트 관련 필요 데이터 저장
from common import get_mysql_connection


POST_CATEGORY = [
    "talk", #잡담
    "share", #책공유
    "info" #책정보
 ]
POST_TYPE = [
    "free", #자유게시판
    "quote", #책 속 문장과 감상
    "line" #한줄평
    ]

conn = get_mysql_connection()
with conn.cursor() as cursor:
    for name in POST_CATEGORY:
        cursor.execute("INSERT INTO post_category (name) VALUES (%s) ON DUPLICATE KEY UPDATE name = VALUES(name)", (name),)
    for name in POST_TYPE:
        cursor.execute("INSERT INTO post_type (name) VALUES (%s) ON DUPLICATE KEY UPDATE name = VALUES(name)", (name),)
conn.commit()
print("커뮤니티 포스트 카테고리와 포스트 타입을 DB에 적재했어요.")
conn.close()