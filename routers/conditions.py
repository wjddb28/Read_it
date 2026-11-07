"""AI 검색 질문에서 장르 조건을 뽑는다. '로맨스 없는 판타지 소설' → 판타지는 포함, 로맨스는 제외.
벡터 검색은 '로맨스 없는'도 로맨스 쪽으로 끌려가므로, 제외 부분은 질문에서 지우고 결과에서 그 장르 책을 거른다.
ponytail: 단어 목록 기반. 목록에 없는 표현('달달한 거 말고')은 못 잡음 → 평가셋에서 놓친 표현이 보이면 단어 추가
"""
import re

# 단어(질문 속 표현의 일부) → 세부 장르 이름 (genre_map.FICTION_SUBGENRES / ESSAY_SUBGENRES)
FICTION_WORDS = {
    "로맨스": ["로맨스", "연애", "사랑 이야기", "사랑 얘기", "사랑이야기", "러브"],
    "추리·미스터리": ["추리", "미스터리"],
    "스릴러·호러": ["스릴러", "호러", "공포", "무서", "무섭", "잔인", "끔찍"],
    "SF": ["SF", "에스에프", "공상과학"],
    "판타지": ["판타지", "마법"],
    "역사 소설": ["역사 소설", "역사소설", "옛날 시대", "시대극"],
    "성장": ["성장"],
    "가족·일상": ["가족"],
    "사회·현실": ["사회 문제", "사회문제", "현실적"],
    "힐링·휴먼": ["힐링"],
}
ESSAY_WORDS = {
    "여행": ["여행"],
    "일상·생활": ["일상"],
    "위로·힐링": ["위로", "힐링"],
    "관계·사랑": ["연애", "사랑"],
    "인생·성찰": ["인생", "성찰"],
    "자연·생태": ["자연", "생태"],
    "일·직업": ["직업", "직장"],
}
ESSAY_HINT = re.compile(r"에세이|산문|수필")
NEG = r"(?:없는|없고|없이|빼고|뺀|말고|제외하고|제외한|아닌|않은|않고|않는|싫어)"
# 부정어 바로 앞 한두 단어: '로맨스(가) 없는', '무섭지 않은', '연애 이야기 빼고', '무서운 장면 없는'
NEG_RE = re.compile(r"(?:(\S+)\s+)?(\S+)\s*" + NEG)


def genres_in(text, table):
    return {genre for genre, words in table.items() if any(w.lower() in text.lower() for w in words)}


def parse_conditions(q):
    """(검색에 쓸 질문, 포함 장르, 제외 장르). 조건이 없으면 질문 그대로와 빈 집합."""
    exclude, kept = set(), q
    for m in NEG_RE.finditer(q):
        prev, word = m.group(1) or "", m.group(2)
        found = genres_in(word, FICTION_WORDS) | genres_in(word, ESSAY_WORDS)
        span = m.span(2)
        if not found and prev:  # '무서운 장면 없는' 처럼 핵심어가 한 단어 앞에 있을 때만 앞 단어까지 본다
            both = f"{prev} {word}"
            found = genres_in(both, FICTION_WORDS) | genres_in(both, ESSAY_WORDS)
            span = m.span(1)
        if found:
            exclude |= found
            kept = kept.replace(q[span[0]:m.end()], " ")
    kept = re.sub(r"\s+", " ", kept).strip()
    include = genres_in(kept, ESSAY_WORDS if ESSAY_HINT.search(kept) else FICTION_WORDS) - exclude
    return kept, include, exclude


if __name__ == "__main__":
    cases = {
        "로맨스 없는 판타지 소설 추천해줘": ({"판타지"}, {"로맨스"}),
        "무섭지 않은 추리 소설 추천해줘": ({"추리·미스터리"}, {"스릴러·호러"}),
        "연애 이야기 빼고 성장 소설 추천해줘": ({"성장"}, {"로맨스", "관계·사랑"}),
        "무서운 장면 없는 SF 소설 읽고 싶어": ({"SF"}, {"스릴러·호러"}),
        "사랑 얘기 말고 가족 이야기 소설 추천해줘": ({"가족·일상"}, {"로맨스", "관계·사랑"}),
        "로맨스가 없는 역사 소설 추천해줘": ({"역사 소설"}, {"로맨스"}),
        "여행 에세이 말고 일상을 다룬 에세이 추천해줘": ({"일상·생활"}, {"여행"}),
        "판타지인데 로맨스 없는 거": ({"판타지"}, {"로맨스"}),
        "비 오는 날 읽기 좋은 책": (set(), set()),
    }
    for q, (inc, exc) in cases.items():
        kept, got_inc, got_exc = parse_conditions(q)
        assert (got_inc, got_exc) == (inc, exc), (q, kept, got_inc, got_exc)
        assert not exc or not genres_in(kept, FICTION_WORDS) & exc, (q, kept)
    print("ok")
