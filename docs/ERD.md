# Read-it DB ERD

> 실제 스키마: [`db/init.sql`](../db/init.sql) — 수정 시 이 파일의 mermaid 블록도 같이 고쳐주세요.

```mermaid
erDiagram
    users {
        INT user_id PK
        VARCHAR(32) login_id "로그인 아이디"
        VARCHAR(255) password_hash "해시 저장"
        VARCHAR(255) email "이메일 로그인"
        VARCHAR(255) google_id "Google sub"
        VARCHAR(32) public_id "공개용 ID"
        VARCHAR(32) nickname "닉네임"
        VARCHAR(32) nickname_key "닉네임 검색 키"
        TEXT about_me "자기소개"
        ENUM gender "M/F/N, NULL"
        SMALLINT birth_year "출생연도"
        BOOLEAN is_suspended
        BOOLEAN onboarded
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    genre {
        INT genre_id PK
        VARCHAR(32) name "장르명"
        INT parent_id FK "상위 장르, NULL"
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    book {
        VARCHAR(13) isbn PK "ChromaDB IDs와 1:1"
        VARCHAR(255) title
        VARCHAR(255) author
        VARCHAR(255) publisher
        SMALLINT publish_year
        TEXT description "줄거리"
        VARCHAR(500) cover_image_url
        VARCHAR(20) kdc_class_no "KDC 분류번호"
        VARCHAR(255) kdc_class_name "KDC 분류명"
        INT genre_id FK
        INT loan_count "정보나루 대출 수"
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    book_subgenre {
        VARCHAR(13) isbn PK,FK
        INT genre_id PK,FK
    }

    book_keyword {
        VARCHAR(13) isbn PK,FK
        VARCHAR(50) word PK
        FLOAT weight
    }

    book_relation {
        VARCHAR(13) isbn PK,FK
        VARCHAR(13) related_isbn PK
        ENUM relation_type PK "CO_LOAN/RECOMMEND"
        FLOAT score
    }

    reading_record {
        INT record_id PK
        INT user_id FK
        VARCHAR(13) isbn FK
        ENUM status "WISH/READING/COMPLETED"
        DATE start_date "NULL"
        DATE end_date "NULL"
        ENUM progress "EARLY/MID/LATE"
        INT review FK "book_review.review_id"
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    daily_reading_log {
        INT record_id PK,FK
        DATE log_date PK
        TEXT content
        SMALLINT reading_minutes
    }

    favorite_genre {
        INT user_id PK,FK
        INT genre_id PK,FK
        ENUM preference "LIKE/DISLIKE"
        TIMESTAMP created_at
    }

    book_review {
        INT review_id PK
        INT user_id FK
        VARCHAR(13) isbn FK
        TINYINT rating "1~5"
        TEXT content
        BOOLEAN has_spoiler
        INT like_count
        INT dislike_count
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    review_reaction {
        INT user_id PK,FK
        INT review_id PK,FK
        ENUM reaction "LIKE/DISLIKE"
        TIMESTAMP created_at
    }

    follows {
        INT follower_id PK,FK
        INT followee_id PK,FK
        TIMESTAMP created_at
    }

    post_category {
        INT category_id PK
        VARCHAR(63) name "카테고리명"
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    post_type {
        INT type_id PK
        VARCHAR(63) name "게시글 타입"
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    community_post {
        INT post_id PK
        INT user_id FK
        INT category_id FK
        INT post_type_id FK
        VARCHAR(100) title
        TEXT content
        INT like_count
        INT dislike_count
        INT view_count
        BOOLEAN is_announcement
        BOOLEAN has_spoiler
        BOOLEAN anonymous
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    post_extra {
        INT post_id PK,FK
        VARCHAR(13) isbn FK "도서 참조"
        TEXT quote
        ENUM spoiler_stage "EARLY/MID/LATE"
        TINYINT rating "1~5"
        ENUM recommend_verdict "RECOMMEND/NOT_RECOMMEND"
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    media {
        INT media_id PK
        INT user_id FK
        INT post_id FK
        BLOB data
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    polls {
        INT poll_id PK
        INT post_id FK
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    poll_options {
        INT option_id PK
        INT poll_id FK
        VARCHAR(255) label
        INT position "옵션 순서"
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    poll_votes {
        INT user_id PK,FK
        INT poll_id FK
        INT option_id PK,FK
        TIMESTAMP created_at
    }

    post_like {
        INT user_id PK,FK
        INT post_id PK,FK
        TIMESTAMP created_at
    }

    post_comment {
        INT comment_id PK
        INT post_id FK
        INT user_id FK
        INT parent_comment_id FK "대댓글, NULL"
        TEXT content
        INT like_count
        INT dislike_count
        BOOLEAN anonymous
        BOOLEAN deleted
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    users ||--o{ reading_record : "서재에 담음"
    book ||--o{ reading_record : ""
    users ||--o{ book_review : "작성"
    book ||--o{ book_review : ""
    book_review ||--o{ review_reaction : ""
    users ||--o{ review_reaction : "누름"
    users ||--o{ favorite_genre : "좋아함/싫어함"
    genre ||--o{ favorite_genre : ""
    users ||--o{ follows : "팔로우함"
    users ||--o{ follows : "팔로워"
    genre |o--o{ genre : "하위 장르"
    genre ||--o{ book : "분류"
    genre ||--o{ book_subgenre : ""
    book ||--o{ book_subgenre : ""
    book ||--o{ book_keyword : "키워드"
    book ||--o{ book_relation : "함께대출/추천"
    users ||--o{ community_post : "작성"
    post_category ||--o{ community_post : ""
    post_type ||--o{ community_post : ""
    community_post ||--|| post_extra : "추가정보"
    community_post ||--o{ media : "미디어"
    community_post ||--|| polls : "투표"
    polls ||--o{ poll_options : "선택지"
    users ||--o{ poll_votes : "투표"
    polls ||--o{ poll_votes : ""
    poll_options ||--o{ poll_votes : ""
    community_post ||--o{ post_like : "좋아요"
    users ||--o{ post_like : "좋아요"
    community_post ||--o{ post_comment : "댓글"
    users ||--o{ post_comment : "작성"
    post_comment |o--o{ post_comment : "대댓글"
    reading_record ||--o{ daily_reading_log : "하루 독서량 기록"
    reading_record ||--o| book_review : "리뷰 연결"
    book_review ||--o{ reading_record : "리뷰 연결"
```
