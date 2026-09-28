-- Read-it MySQL 스키마 초안 (MySQL 8.0, utf8mb4)
-- ERD(my erd) 기반 + 리뷰 반영본. 팀 확정 전 초안입니다.

CREATE DATABASE IF NOT EXISTS read_it_db
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE read_it_db;

-- =========================================================
-- 1. 사용자
-- =========================================================
CREATE TABLE users (
  user_id        INT AUTO_INCREMENT PRIMARY KEY,
  login_id       VARCHAR(32)  NOT NULL UNIQUE,          -- 로그인 아이디 (ERD의 id)
  password_hash  VARCHAR(255) NOT NULL,                 -- bcrypt 등 해시값 저장 (평문 X)
  nickname       VARCHAR(32)  NOT NULL,                 -- ERD의 username
  gender         ENUM('M','F','N') NULL,
  birth_year     SMALLINT NULL,                         -- age 대신 출생연도 (나이는 계산)
  is_suspended   BOOLEAN NOT NULL DEFAULT FALSE,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
-- book_count, total_time 은 reading_record 로 집계 가능하므로 제거 (필요 시 뷰/쿼리로 계산)

-- =========================================================
-- 2. 장르 / 도서
-- =========================================================
CREATE TABLE genre (
  genre_id    INT AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(32) NOT NULL UNIQUE,
  parent_id   INT NULL,                                  -- 하위장르(subgenre)는 parent_id 로 표현
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (parent_id) REFERENCES genre(genre_id)
);

CREATE TABLE book (
  isbn             VARCHAR(13)  PRIMARY KEY,             -- ChromaDB ids 와 1:1
  title            VARCHAR(255) NOT NULL,
  author           VARCHAR(255) NOT NULL,
  publisher        VARCHAR(255) NULL,
  publish_year     SMALLINT NULL,
  description      TEXT NULL,                            -- 줄거리 (임베딩 원문)
  cover_image_url  VARCHAR(500) NULL,
  kdc_class_no     VARCHAR(20)  NULL,                    -- 정보나루 KDC 분류번호 (예: 813.7)
  kdc_class_name   VARCHAR(255) NULL,                    -- 정보나루 KDC 분류명
  genre_id         INT NULL,
  loan_count       INT NOT NULL DEFAULT 0,               -- 정보나루 대출 횟수 (인기도)
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (genre_id) REFERENCES genre(genre_id),
  INDEX idx_book_title (title),
  INDEX idx_book_author (author)
);

-- 정보나루 키워드 API: 책 1권에 키워드 여러 개 + 가중치
CREATE TABLE book_keyword (
  isbn    VARCHAR(13) NOT NULL,
  word    VARCHAR(50) NOT NULL,
  weight  FLOAT NOT NULL DEFAULT 0,
  PRIMARY KEY (isbn, word),
  FOREIGN KEY (isbn) REFERENCES book(isbn) ON DELETE CASCADE,
  INDEX idx_keyword_word (word)
);

-- 정보나루 추천도서 / 함께 대출된 도서
CREATE TABLE book_relation (
  isbn          VARCHAR(13) NOT NULL,
  related_isbn  VARCHAR(13) NOT NULL,
  relation_type ENUM('CO_LOAN','RECOMMEND') NOT NULL,
  score         FLOAT NULL,
  PRIMARY KEY (isbn, related_isbn, relation_type),
  FOREIGN KEY (isbn) REFERENCES book(isbn) ON DELETE CASCADE
  -- related_isbn 은 우리 DB에 없는 책일 수 있어 FK 미설정
);

-- =========================================================
-- 3. 서재 (독서 기록) — 찜하기는 status = 'WISH' 로 통합
-- =========================================================
CREATE TABLE reading_record (
  record_id        INT AUTO_INCREMENT PRIMARY KEY,
  user_id          INT NOT NULL,
  isbn             VARCHAR(13) NOT NULL,
  status           ENUM('WISH','READING','COMPLETED') NOT NULL DEFAULT 'WISH',
  start_date       DATE NULL,                            -- WISH 상태에서는 NULL
  end_date         DATE NULL,                            -- COMPLETED 시 입력
  reading_minutes  INT NOT NULL DEFAULT 0,               -- ERD의 time
  created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_record_user_book (user_id, isbn),
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (isbn)    REFERENCES book(isbn),
  INDEX idx_record_user_status (user_id, status)
);

-- 장르 즐겨찾기 (다대다 연결 테이블)
CREATE TABLE favorite_genre (
  user_id     INT NOT NULL,
  genre_id    INT NOT NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, genre_id),
  FOREIGN KEY (user_id)  REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (genre_id) REFERENCES genre(genre_id) ON DELETE CASCADE
);

-- =========================================================
-- 4. 리뷰 (별점 + 감상평)
-- =========================================================
CREATE TABLE book_review (
  review_id    INT AUTO_INCREMENT PRIMARY KEY,
  user_id      INT NOT NULL,
  isbn         VARCHAR(13) NOT NULL,
  rating       TINYINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  content      TEXT NULL,
  has_spoiler  BOOLEAN NOT NULL DEFAULT FALSE,
  like_count   INT NOT NULL DEFAULT 0,                   -- review_reaction 집계 캐시
  dislike_count INT NOT NULL DEFAULT 0,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_review_user_book (user_id, isbn),        -- 한 사람당 책 1권에 리뷰 1개
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (isbn)    REFERENCES book(isbn)
);

-- 좋아요/싫어요 중복 방지용 (누가 눌렀는지 기록)
CREATE TABLE review_reaction (
  user_id    INT NOT NULL,
  review_id  INT NOT NULL,
  reaction   ENUM('LIKE','DISLIKE') NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, review_id),
  FOREIGN KEY (user_id)   REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (review_id) REFERENCES book_review(review_id) ON DELETE CASCADE
);

-- =========================================================
-- 5. 커뮤니티 (우선순위 낮음)
-- =========================================================
CREATE TABLE post_category (
  category_id  INT AUTO_INCREMENT PRIMARY KEY,
  name         VARCHAR(63) NOT NULL UNIQUE,
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE community_post (
  post_id         INT AUTO_INCREMENT PRIMARY KEY,
  user_id         INT NOT NULL,
  category_id     INT NOT NULL,
  title           VARCHAR(100) NOT NULL,
  content         TEXT NOT NULL,
  like_count      INT NOT NULL DEFAULT 0,
  dislike_count   INT NOT NULL DEFAULT 0,
  view_count      INT NOT NULL DEFAULT 0,
  is_announcement BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id)     REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES post_category(category_id)
);

CREATE TABLE post_comment (
  comment_id        INT AUTO_INCREMENT PRIMARY KEY,
  post_id           INT NOT NULL,
  user_id           INT NOT NULL,
  parent_comment_id INT NULL,                            -- 대댓글이면 부모 댓글 id, 아니면 NULL
  content           TEXT NOT NULL,
  like_count        INT NOT NULL DEFAULT 0,
  dislike_count     INT NOT NULL DEFAULT 0,
  created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (post_id)           REFERENCES community_post(post_id) ON DELETE CASCADE,
  FOREIGN KEY (user_id)           REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (parent_comment_id) REFERENCES post_comment(comment_id) ON DELETE CASCADE
);
