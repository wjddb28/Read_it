# 리딧 (Read-it)

AI 기반 맞춤형 도서 기록 및 추천 플랫폼 — 2026-2 캡스톤디자인

## 로컬 개발 환경 세팅

### 1. 준비물
- Python 3.11
- MySQL 8.0 (로컬 설치)
- Node.js 22 이상 (React 화면, 설치 후 `npm install`)

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
| `GET /api/books/search?q=&by=all\|title\|author\|isbn\|keyword` | 정보나루 실시간 도서 검색 (판본 묶음, `in_db` 표시). `all` 은 제목·저자·키워드 결과를 합침 | `routers/books.py` |
| `GET /api/search?q=&ai=false\|true` | 검색창용. `ai=false` 일반 검색(제목·저자·ISBN, 결과 없으면 `message`+`suggest_ai`), `ai=true` AI 추천 검색(맥락 없는 입력은 `mode=retry`+DB 무작위 5권+검색 예시 문구). "○○와 비슷한 책"이면 그 책 기준으로 추천(`similar_to`, 같은 작가·시리즈는 `same_author`, 추천 이유 `match`) | `routers/search.py` |
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

DB에 없는 책을 서재에 담을 때는 `routers/books.py` 의 `add_to_db(isbn)` (내부적으로 `scripts/book_store.py` 의 `ensure_book()`) 을 호출하면
정보나루에서 받아 MySQL + ChromaDB 에 저장하고 문학이면 상세 장르도 붙입니다. (같은 작품의 다른 판본이면 기존 ISBN을 돌려줌, 없는 ISBN은 404)

### 구글 로그인 데이터 저장

`routers/auth.py` 의 로그인은 Google ID token을 검증한 뒤 `users` 테이블에서 `google_id` 로 사용자를 찾습니다.
처음 로그인하면 Google의 고유 ID(`sub`), 이메일, 닉네임을 MySQL에 저장하고, 다음 로그인부터는 이메일과 닉네임을 갱신합니다.
Google 비밀번호나 ID token은 데이터베이스에 저장하지 않습니다. API의 사용자 `id`는 기존 프론트엔드 서재와의 호환성을 위해 `google:<sub>` 형태로 유지합니다.

개발 서버의 `.env` 에 MySQL 연결 정보(`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`)를 설정하고,
`db/init.sql` 의 `users` 테이블에 `email` 및 `google_id` 열이 존재해야 합니다. 이전 스키마로 이미 테이블을 만든 경우, 아직 없는 열을 추가하고
Google 계정 사용을 위해 `login_id` 및 `password_hash` 가 `NULL` 을 허용하도록 변경됬습니다. 로그인 세션 쿠키와 세션 정보는 여전히 서버 메모리에만 있으므로 서버를 재시작하면 다시 로그인해야 합니다.

## 검색이 안 될 때 체크리스트

### 1. 최신 코드인지
- [ ] `git pull` 로 main 최신 코드를 받았나요?
- [ ] 받은 뒤 서버를 껐다 켰나요?

### 2. 서버 두 개가 켜져 있는지
- [ ] 터미널 1: `python -m uvicorn main:app --reload` → `Application startup complete` 가 떴나요?
- [ ] 터미널 2: `npm run dev` → `Local: http://localhost:5173/` 이 떴나요?
- [ ] 브라우저에서 **http://localhost:5173** 으로 접속했나요? (8000번이나 HTML 파일을 직접 열면 안 됨)
- [ ] `Port 5173 is already in use` 가 뜨면 이전에 켠 `npm run dev` 터미널을 닫고 다시 실행해요.

### 3. 패키지 설치
- [ ] `pip install -r requirements.txt` 를 다시 했나요? (최근 `google-auth`, `httpx` 추가)
- [ ] `npm install` 을 했나요? (`node_modules` 폴더가 있어야 함)

### 4. `.env` 파일
- [ ] 프로젝트 맨 위 폴더에 `.env` 가 있나요? (`.env.example` 을 복사해서 만듦)
- [ ] 아래 값이 다 채워져 있나요?

| 값 | 없으면 생기는 일 |
|---|---|
| `LIBRARY_API_KEY` | 일반 검색·인기 도서 전부 실패 |
| `MYSQL_PASSWORD` 등 MySQL 값 | 검색 결과 표시·AI 검색 실패 |
| `GEMINI_API_KEY` | 서버 시작 또는 AI 검색 실패 |

### 5. DB 준비
- [ ] MySQL이 실행 중인가요?
- [ ] `python scripts/load_seed.py` 를 한 번 실행했나요? (마지막에 `ChromaDB 적재 완료: 5004건`)
- [ ] 프로젝트 경로에 한글이 있으면 ChromaDB가 못 읽어요 → `.env` 에 `CHROMA_DIR=C:/readit_chroma` 처럼 영문 경로를 넣고 `load_seed.py` 다시 실행

### 6. 정보나루 API 키
- [ ] 각자 발급한 키라면 IP 등록 전에는 하루 500회 제한이에요. 테스트를 많이 하면 막혀요.

### 오류 코드로 원인 찾기
uvicorn 터미널 로그나 브라우저 개발자 도구(F12 → Network)에서 `/api/...` 요청의 숫자를 보세요.

| 숫자 | 원인 | 확인할 곳 |
|---|---|---|
| **422** | 예전 코드 (예: "전체" 검색 미지원) | 1번 |
| **502** | 정보나루 호출 실패 (키 없음·하루 한도·인터넷) | 4번, 6번 |
| **503** | AI 검색 준비 실패 (ChromaDB 없음·경로 한글) | 5번 |
| **500** | MySQL 연결 실패 (꺼짐·비밀번호·DB 없음) | 4번, 5번 |
| **404 / 연결 거부** | uvicorn(8000)이 꺼져 있음 | 2번 |

**빠른 확인:** http://localhost:8000/docs 에서 `GET /api/books/search` → **Try it out** 으로 검색해 보면 화면 문제인지 서버 문제인지 바로 구분돼요.

## AI 검색 정확도 평가
`eval/questions.jsonl` 의 질문 49개(정답 책형·장르형·부정 조건형)로 AI 추천 검색을 채점합니다.
검색 로직을 바꾸기 전후에 같은 DB로 돌려 비교하세요. 지표 설명은 `scripts/eval_search.py` 맨 위에 있습니다.
```bash
python scripts/eval_search.py --name baseline            # 채점 → eval/results/baseline.json
python scripts/eval_search.py --name after               # 고도화 후 다시 채점
python scripts/eval_search.py --compare baseline after   # 나란히 비교
```
- 고도화를 조정할 때는 `split: dev` 질문만 보고, `test` 질문은 마지막 비교에만 씁니다.
- 질문을 고치면 기준선(baseline)도 다시 채점해야 비교가 공정합니다.

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
서재 담기 등으로 DB에 새로 들어오는 책은 `ensure_book()` 이 저장할 때 자동으로 분류합니다(Gemini 실패 시 장르 없이 저장).
장르가 빈 채로 저장된 책은 `python scripts/classify_genres.py --db` 로 나중에 채웁니다.
