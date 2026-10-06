# routers/test.py
# 지금은 테스트용, 나중에 개인 서재 기능에 통합될 예정
# 현재 작동 안함!!!

from books import search_books

from common import get_mysql_connection
# ^^ 이게 안됨 ;;

sql = get_mysql_connection()

search_term = input("검색어를 입력하세요: ");

sql.cursor().execute("""SELECT title FROM book WHERE title LIKE %s""", (f"%{search_term}%",))
result = sql.cursor().fetchall()

print(f"검색어 '{search_term}'에 대한 결과:")
for row in result:
    print(row["title"])
    
if not result:
    print("검색 결과가 없습니다. 외부 API에서 검색을 시도합니다.")
    search_result = search_books(q=search_term, by="title", page=1, size=5)
    for book in search_result:
        print(f"제목: {book['title']}, 저자: {book['author']}, ISBN: {book['isbn']}")
    
    save_to_db = input("이 책들을 DB에 저장하시겠습니까? (y/n): ")
    if save_to_db.lower() == 'y':
        conn = get_mysql_connection()
        try:
            with conn.cursor() as cur:
                for book in search_result:
                    cur.execute(
                        """INSERT INTO book (isbn, title, author, publisher, publish_year, cover_image_url)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (book["isbn"], book["title"], book["author"], book.get("publisher"), book.get("publish_year"), book.get("cover_image_url"))
                    )
            conn.commit()
            print("책 정보가 DB에 저장되었습니다.")
        finally:
            conn.close()
    else:
        print("책 정보가 DB에 저장되지 않았습니다.")