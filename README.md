# 리딧 (Read-it)

AI 기반 맞춤형 도서 기록 및 추천 플랫폼 — 2026-2 캡스톤디자인

## 로컬 개발 환경 세팅

### 1. 준비물
- Python 3.11
- MySQL 8.0 (로컬 설치)

### 2. 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. 환경변수
`.env.example` 을 복사해 `.env` 를 만들고 본인 MySQL 비밀번호를 입력합니다.
`.env` 는 git에 올라가지 않습니다.

```
MYSQL_PASSWORD=본인_비밀번호
```

### 4. DB 생성 + 시드 데이터 적재
```bash
python scripts/load_seed.py --reset
```
- `db/init.sql` 로 `read_it_db` 의 테이블을 만들고
- `seed/books.jsonl` 의 도서를 MySQL(`book`, `book_keyword`, `book_relation`, `genre`)에 넣고
- 도서 임베딩을 `chroma_data/` 에 생성합니다. (최초 실행 시 임베딩 모델 다운로드로 수 분 소요)

> ⚠️ `--reset` 은 `read_it_db` 를 통째로 지우고 다시 만듭니다. 로컬에서 만든 테스트 계정·서재 데이터도 사라집니다.
> 도서 데이터만 갱신하려면 `--reset` 없이 실행하세요.

## 데이터 구조

| 위치 | 내용 | git |
|---|---|---|
| `db/init.sql` | MySQL 스키마 | ✅ |
| `seed/books.jsonl` | 정보나루 인기대출도서 시드 데이터 | ✅ |
| `scripts/genre_map.py` | KDC 분류번호 → 장르 매핑 | ✅ |
| `chroma_data/` | 도서 줄거리 임베딩 (load_seed로 각자 생성) | ❌ |
| `seed/raw/` | 정보나루 API 원본 응답 캐시 | ❌ |

MySQL `book.isbn` 과 ChromaDB `ids` 가 1:1로 매칭됩니다.

## 시드 데이터 수집 (수집 담당자만)
정보나루 API 키를 `.env` 의 `LIBRARY_API_KEY` 에 넣고 실행합니다.
```bash
python scripts/fetch_books.py --target 1000 --max-calls 450
```
- IP 미등록 키는 하루 500회 제한 → 한도에 걸리면 다음 날 같은 명령으로 이어서 수집
- 아동·학습참고서 제외, 같은 책의 다른 판본은 하나로 합침
- 결과 `seed/books.jsonl` 을 커밋하면 팀원은 `load_seed.py` 만 실행하면 됩니다
