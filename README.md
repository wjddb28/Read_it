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
  - ⚠️ ChromaDB는 경로에 **한글**이 있으면 1,000건 이상일 때 다시 읽지 못합니다. 프로젝트 경로에 한글이 있으면 자동으로 홈 폴더의 `.readit/chroma_data` 를 쓰고, 다른 위치를 쓰려면 `.env` 에 `CHROMA_DIR` 을 지정하세요.

> ⚠️ `--reset` 은 `read_it_db` 를 통째로 지우고 다시 만듭니다. 로컬에서 만든 테스트 계정·서재 데이터도 사라집니다.
> 도서 데이터만 갱신하려면 `--reset` 없이 실행하세요.

### 5. 서버 실행
```bash
uvicorn main:app --reload
```
http://localhost:8000/docs 에서 API를 테스트할 수 있습니다.

| API | 기능 | 파일 |
|---|---|---|
| `GET /api/books/search?q=&by=title\|author\|isbn\|keyword` | 정보나루 실시간 도서 검색 (판본 묶음, `in_db` 표시) | `routers/books.py` |
| `GET /api/search?q=&ai=false\|true` | 검색창용. `ai=false` 일반 검색(제목·저자·ISBN, 결과 없으면 `message`+`suggest_ai`), `ai=true` AI 추천 검색(맥락 없는 입력은 `mode=retry`+DB 무작위 5권+검색 예시 문구) | `routers/search.py` |
| `POST /api/recommend` | 자연어 AI 추천 (ChromaDB + Gemini) | `routers/recommend.py` |
| `GET /api/books/popular?limit=10` | 최근 30일 정보나루 인기 대출 도서 (`start`, `end`, `books[].ranking`, 하루 1번만 정보나루 호출) | `routers/books.py` |
| `GET /api/books/{isbn}` | 도서 상세 (DB에 없으면 정보나루에서 조회) | `routers/books.py` |

### 프론트엔드(React)에서 부르기

FastAPI(`uvicorn main:app --reload`, 8000번)와 Vite(`npm run dev`, 5173번)를 같이 켜고 http://localhost:5173 으로 접속합니다.
Vite가 `/api` 요청을 8000번으로 넘겨주므로(`vite.config.js` 의 proxy) React에서는 `/api/...` 상대 경로로 부르면 됩니다.

```js
// 검색창: ai=false 일반 검색, ai=true AI 추천 검색, comment=true 면 추천 코멘트(약 2초)
const res = await fetch(`/api/search?q=${encodeURIComponent(q)}&ai=${ai}`);
const data = await res.json();
// data.mode: "general" | "ai" | "retry"
// data.books: 책 카드 목록, data.message: 안내 문구(결과 없음·retry일 때)
// data.suggest_ai: true 면 "AI 검색으로 가볼까요?" 버튼 표시, data.ai_comment: 추천 코멘트(없으면 null)

const popular = await (await fetch(`/api/books/popular?limit=5`)).json(); // { start, end, books: [...] }
```

책 카드 필드: `isbn, title, author, publisher, publish_year, cover_image_url` (DB에서 온 책은 `description` 도 포함,
일반 검색 결과는 우리 DB에 있는 책인지 `in_db` 표시). `cover_image_url` 이 비어 있을 수 있으니 기본 표지를 준비하세요.

DB에 없는 책을 서재에 담을 때는 `scripts/book_store.py` 의 `ensure_book(isbn, ...)` 을 호출하면
정보나루에서 받아 MySQL + ChromaDB 에 저장합니다. (같은 작품의 다른 판본이면 기존 ISBN을 돌려줌)

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

### 문학 상세 장르 분류 (main 브랜치에서)
`.env` 의 `GEMINI_API_KEY` 로 문학 도서(소설·에세이·시·희곡·기타 문학)에 상세 장르를 1~3개씩 붙여 `books.jsonl` 의 `subgenres` 에 저장합니다.
장르 목록은 `scripts/genre_map.py` 의 `FICTION_SUBGENRES`(이야기책) / `ESSAY_SUBGENRES`(에세이·시) 입니다.
```bash
python scripts/classify_genres.py --sample 50   # 50권만 분류해 결과 확인 (저장 안 함)
python scripts/classify_genres.py               # 전체 분류 (이미 붙은 책은 건너뜀)
python scripts/load_seed.py                     # MySQL book_subgenre 테이블에 반영
```
