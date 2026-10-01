"""정보나루 제목·저자 정리 규칙 확인: python scripts/test_clean.py"""
from fetch_books import clean_author, clean_title

AUTHORS = {
    "지은이: 히가시노 게이고 ;옮긴이: 김윤경": "히가시노 게이고",
    "앤디 위어 지음 ;강동혁 옮김": "앤디 위어",
    "프랑수아즈 사강 [지음]": "프랑수아즈 사강",
    "원작·각색: 유발 하라리": "유발 하라리",
    "찰리 맥커시 글·그림": "찰리 맥커시",
    "멜 로빈스,윤효원 옮김": "멜 로빈스",
    "한로로 (HANRORO) (지은이)": "한로로 (HANRORO)",
    "김글": "김글",
    "유시민,사진: 한경혜": "유시민",
    "강방천,일러스트: 정민영": "강방천",
}
TITLES = {
    "소년이 온다 :한강 장편소설": "소년이 온다",
    "채식주의자:한강 연작소설": "채식주의자",
    "종의 기원 =정유정 장편소설 /The origin of species": "종의 기원",
    "(2500년 동안 사랑받은) 초역 부처의 말": "초역 부처의 말",
    "1984": "1984",
}

for raw, want in AUTHORS.items():
    assert clean_author(raw) == want, (raw, clean_author(raw))
for raw, want in TITLES.items():
    assert clean_title(raw) == want, (raw, clean_title(raw))
print("ok")
