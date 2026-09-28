"""
KDC 분류번호 → Read-it 장르 매핑 (초안, 팀 논의 후 수정).

문학(8xx)은 세 번째 자리(형식)로 나눈다: 8x1 시, 8x3 소설, 8x4 수필 ...
그 외는 KDC 주류(첫 자리) 기준.
"""

# (장르명, 상위 장르명 or None) — genre 테이블 시드 순서
GENRES = [
    ("문학", None),
    ("소설", "문학"),
    ("시", "문학"),
    ("에세이", "문학"),
    ("희곡", "문학"),
    ("기타 문학", "문학"),
    ("인문", None),
    ("철학", "인문"),
    ("종교", "인문"),
    ("역사", "인문"),
    ("언어", "인문"),
    ("사회과학", None),
    ("경제경영", "사회과학"),
    ("자연과학", None),
    ("기술과학", None),
    ("예술", None),
    ("총류", None),
]

LITERATURE_FORM = {"1": "시", "2": "희곡", "3": "소설", "4": "에세이"}
MAIN_CLASS = {
    "0": "총류", "1": "철학", "2": "종교", "3": "사회과학", "4": "자연과학",
    "5": "기술과학", "6": "예술", "7": "언어", "9": "역사",
}


def kdc_to_genre(class_no):
    """'813.7' → '소설'. 알 수 없으면 None."""
    digits = "".join(c for c in (class_no or "") if c.isdigit())
    if not digits:
        return None
    if digits[0] == "8":
        return LITERATURE_FORM.get(digits[2:3], "기타 문학")
    if digits[:2] in ("32", "33"):  # 32x 경제학, 325 경영
        return "경제경영" if digits[:2] == "32" else "사회과학"
    return MAIN_CLASS.get(digits[0])
