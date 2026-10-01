"""통합 검색의 질문 분류 규칙 확인: python test_search_route.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from routers.search import classify_query, smart_search  # noqa: E402

CASES = {
    "9788936434120": "isbn",
    "978-89-364-3412-0": "isbn",
    "한강": "keyword",
    "히가시노 게이고": "keyword",
    "나미야 잡화점의 기적": "keyword",
    "해리 포터와 마법사의 돌": "keyword",
    "당신의 인생이 왜 힘들지 않아야 한다고 생각하십니까": "keyword",
    "비 오는 날 읽기 좋은 위로가 되는 소설": "ai",
    "현대 판타지인데 로맨스가 없는 책 추천해줘": "ai",
    "데미안 같은 성장소설": "ai",
    "잠들기 전에 읽을 만한 따뜻한 책": "ai",
    "뮻뮻뮻": "retry",
    "zzz": "retry",
    "뷁뷁": "retry",
    "ㅋㅋㅋㅋ": "retry",
    "12345": "retry",
    "...": "retry",
    "모순": "keyword",
    "1Q84": "keyword",
}
for q, want in CASES.items():
    assert classify_query(q) == want, (q, classify_query(q))
# 엉뚱한 입력 예시와 비슷하면 API 호출 없이 다시 입력 요청 (모델만 사용)
for q in ["asdfasdf", "심심하다", "아무거나 추천", "몰라요", "테스트입니다"]:
    assert smart_search(q=q, top_k=5, comment=False)["mode"] == "retry", q
print("ok")
