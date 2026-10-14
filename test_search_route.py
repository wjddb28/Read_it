"""검색 동작 확인 (정보나루·Gemini·MySQL 호출 없음): python test_search_route.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import routers.search as search  # noqa: E402

# 일반 검색: ISBN이면 ISBN 검색, 아니면 제목+저자 검색
calls = []
search.search_books = lambda q, by, page, size: calls.append((q, by)) or {"books": []}
search.random_books = lambda n=5: [{"isbn": "x"}] * n
for q, want in {"978-89-364-3412-0": [("9788936434120", "isbn")],
                "한강": [("한강", "title"), ("한강", "author")],
                "1Q84": [("1Q84", "title"), ("1Q84", "author")]}.items():
    calls.clear()
    res = search.smart_search(q=q, ai=False, top_k=5, comment=False)
    assert sorted(calls) == sorted(want), (q, calls)
    # 결과가 없으면 안내 문구 + AI 검색 제안
    assert res["books"] == [] and res["suggest_ai"] and res["message"] == search.NOT_FOUND_MESSAGE, res

# 일반 검색은 엉뚱한 입력 검사를 하지 않는다 (실제 '안녕'이라는 책이 있음)
calls.clear()
search.smart_search(q="안녕", ai=False, top_k=5, comment=False)
assert calls, "일반 검색에서 '안녕'도 정보나루로 검색해야 함"

# AI 검색: 엉뚱한 입력은 다시 입력 요청
for q in ["뷁뷁", "zzz", "ㅋㅋㅋㅋ", "12345", "...", "asdfasdf", "몰라요", "테스트입니다", "안녕하세요", "hello"]:
    res = search.smart_search(q=q, ai=True, top_k=5, comment=False)
    assert res["mode"] == "retry" and len(res["books"]) == 5, q
# AI 검색: 정상 질문은 통과
for q in ["심심해", "심심하다", "뭐하지", "아무거나 추천", "우울해", "비 오는 날 읽기 좋은 잔잔한 소설", "우주를 배경으로 한 성장 이야기", "회사 생활이 힘들 때 위로가 되는 책"]:
    assert not search.is_nonsense(q), q
# '○○와 비슷한 책': 질문에서 책 제목만 뽑는다 (패턴이 아니면 None → 일반 AI 추천)
from routers.similar import title_in_query  # noqa: E402
for q, want in {"앨리스죽이기 와 비슷한 책 추천해줘.": "앨리스죽이기", "『앨리스 죽이기』 같은 책": "앨리스 죽이기",
                "죄와 벌과 비슷한 책": "죄와 벌", "불편한 편의점 같은 따뜻한 소설 추천해줘": "불편한 편의점",
                "해리포터 같은 판타지 추천": "해리포터", "소년이 온다 같은책": "소년이 온다",
                "비 오는 날 읽기 좋은 책": None, "로맨스 없는 판타지 소설 추천해줘": None}.items():
    assert title_in_query(q) == want, (q, title_in_query(q))
# 정보나루 줄거리 HTML 기호 정리
from fetch_books import clean_text  # noqa: E402
assert clean_text("&lt;망원동 브라더스&gt;의 작가") == "<망원동 브라더스>의 작가"
assert clean_text("확정&#x0D;『오늘 밤』&#x0D;&#x0D;&#x0D;&#x0D;출간") == "확정\n『오늘 밤』\n\n출간"
assert clean_text("초인(&#220;bermensch)") == "초인(Übermensch)" and clean_text("&lt;편지&g; 리커버") == "<편지> 리커버"
assert clean_text(None) == ""
print("ok")
