"""routers/personal.py 확인용: 임시 사용자를 만들어 시나리오별 추천을 보고, 끝나면 지운다.
    python scripts/check_personal.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import get_mysql_connection  # noqa: E402
from routers.personal import personal_books  # noqa: E402

TEST_GOOGLE_ID = "check-personal-test"


def books_by(cur, author, n):
    cur.execute("SELECT isbn, title FROM book WHERE author = %s ORDER BY loan_count DESC LIMIT %s", (author, n))
    return cur.fetchall()


def subgenre_book(cur, name):
    cur.execute("""SELECT b.isbn, b.title, b.author FROM book b JOIN book_subgenre bs ON bs.isbn = b.isbn
                   JOIN genre g ON g.genre_id = bs.genre_id WHERE g.name = %s ORDER BY b.loan_count DESC LIMIT 1""", (name,))
    return cur.fetchone()


def tags_of(cur, isbns):
    cur.execute("""SELECT bs.isbn, g.name FROM book_subgenre bs JOIN genre g ON g.genre_id = bs.genre_id
                   WHERE bs.isbn IN %s""", (tuple(isbns),))
    out = {}
    for r in cur.fetchall():
        out.setdefault(r["isbn"], set()).add(r["name"])
    return out


def main():
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE google_id = %s", (TEST_GOOGLE_ID,))
            cur.execute("INSERT INTO users (google_id, nickname) VALUES (%s, '추천테스트')", (TEST_GOOGLE_ID,))
            uid = cur.lastrowid
            conn.commit()

            print("[1] 서재 기록 없음 + 선호 판타지 / 비선호 로맨스")
            got = personal_books(uid, ["판타지"], ["로맨스"])
            tags = tags_of(cur, [b["isbn"] for b in got]) if got else {}
            for b in got:
                print("   ", b["title"], b["reasons"], sorted(tags.get(b["isbn"], [])))
            assert got and all("판타지" in tags.get(b["isbn"], set()) for b in got)
            assert not any("로맨스" in tags.get(b["isbn"], set()) for b in got)
            assert personal_books(uid) == []

            fav = books_by(cur, "히가시노 게이고", 3)
            romance = subgenre_book(cur, "로맨스")
            for b, rating, comment in [(fav[0], 5, "반전이 대단했다"), (fav[1], 4, None),
                                       (romance, 1, "너무 뻔한 연애 이야기라 별로였다")]:
                cur.execute("INSERT INTO reading_record (user_id, isbn, status) VALUES (%s, %s, 'COMPLETED')", (uid, b["isbn"]))
                cur.execute("INSERT INTO book_review (user_id, isbn, rating, content) VALUES (%s, %s, %s, %s)",
                            (uid, b["isbn"], rating, comment))
            conn.commit()

            print(f"\n[2] 히가시노 게이고 5·4점, 로맨스 「{romance['title']}」({romance['author']}) 1점")
            got = personal_books(uid, [], ["로맨스"])
            tags = tags_of(cur, [b["isbn"] for b in got])
            for b in got:
                print("   ", b["title"], "/", b["author"], b["reasons"], sorted(tags.get(b["isbn"], [])))
            read = {fav[0]["isbn"], fav[1]["isbn"], romance["isbn"]}
            assert len(got) == 6 and not read & {b["isbn"] for b in got}, "이미 읽은 책은 빼야 함"
            assert any("자주 읽은 작가" in r for b in got for r in b["reasons"]), "자주 읽은 작가 책이 있어야 함"
            assert sum(b["author"] == "히가시노 게이고" for b in got) <= 2, "작가당 최대 2권"
            assert not any(b["author"] == romance["author"] for b in got), "낮게 준 작가는 빼야 함"
            assert not any("로맨스" in tags.get(b["isbn"], set()) for b in got), "비선호 장르는 빼야 함"
            print("\nok")
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM book_review WHERE user_id IN (SELECT user_id FROM users WHERE google_id = %s)",
                        (TEST_GOOGLE_ID,))
            cur.execute("DELETE FROM users WHERE google_id = %s", (TEST_GOOGLE_ID,))
        conn.commit()
        conn.close()


if __name__ == "__main__":
    main()
