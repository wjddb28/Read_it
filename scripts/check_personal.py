"""routers/personal.py 확인용: 임시 사용자를 만들어 시나리오별 추천을 보고, 끝나면 지운다.
    python scripts/check_personal.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["READIT_COMMUNITY_DB"] = str(Path(tempfile.mkdtemp()) / "check.sqlite3")  # 실제 커뮤니티 DB는 건드리지 않음

from common import get_mysql_connection  # noqa: E402
from routers.community_store import database, ensure_profile  # noqa: E402
from routers.personal import finished_works, personal_books  # noqa: E402
from routers.search import smart_search  # noqa: E402

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

            print("\n[3] 자연어 검색 개인화 (선호 추리·미스터리 / 비선호 로맨스)")
            assert finished_works([{"title": "a", "author": "b", "status": "WISH"}]) == set()
            user = {"id": "google:" + TEST_GOOGLE_ID}
            with database() as db:
                ensure_profile(db, user)
                db.execute("UPDATE profiles SET liked=?, disliked=? WHERE owner=?",
                           (json.dumps(["추리·미스터리"], ensure_ascii=False), json.dumps(["로맨스"], ensure_ascii=False), user["id"]))

            def search(q, who):
                return smart_search(q=q, ai=True, top_k=10, comment=False, user=who)["books"]

            q = "마음이 따뜻해지는 소설 추천해줘"
            plain, mine = search(q, None), search(q, user)
            tags = tags_of(cur, [b["isbn"] for b in plain + mine])
            print("    일반:", [b["title"] for b in plain])
            print("    맞춤:", [b["title"] for b in mine])
            assert [b["isbn"] for b in plain] != [b["isbn"] for b in mine], "서재 기록이 있으면 결과가 달라져야 함"
            assert not read & {b["isbn"] for b in mine}, "이미 읽은 책은 빼야 함"
            assert not any(b["author"] == romance["author"] for b in mine), "낮게 준 작가는 빼야 함"
            assert not any("로맨스" in tags.get(b["isbn"], set()) for b in mine), "비선호 장르는 빼야 함"

            q = "판타지 소설 추천해줘"
            plain, mine = search(q, None), search(q, user)
            tags = tags_of(cur, [b["isbn"] for b in plain + mine])
            count = lambda books: sum("판타지" in tags.get(b["isbn"], set()) for b in books)
            print("    판타지 비율:", count(plain), "→", count(mine), "/ 10")
            assert count(mine) >= count(plain), "질문 장르가 취향보다 우선이어야 함"

            mine = search("로맨스 소설 추천해줘", user)
            tags = tags_of(cur, [b["isbn"] for b in mine])
            print("    로맨스를 직접 요청:", sum("로맨스" in tags.get(b["isbn"], set()) for b in mine), "/ 10")
            assert any("로맨스" in tags.get(b["isbn"], set()) for b in mine), "질문이 비선호보다 우선이어야 함"

            base_book = books_by(cur, "히가시노 게이고", 4)[3]["title"]
            res = smart_search(q=f"{base_book}와 비슷한 책 추천해줘", ai=True, top_k=10, comment=False, user=user)
            assert res.get("similar_to") and not read & {b["isbn"] for b in res["books"] + res["same_author"]}, "비슷한 책에서도 읽은 책은 빼야 함"

            stranger = {"id": "google:check-personal-none"}  # MySQL 계정이 없어도 검색은 그대로
            assert [b["isbn"] for b in search(q, stranger)] == [b["isbn"] for b in plain]
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
