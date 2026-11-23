"""Apply the schema additions from commit 0452e92 to an existing MySQL database."""
"""(changes from the Nov 11 commit. changes can be seen in the image in the docs folder)"""
"""does not need to be run if 'python scripts/load_seed.py --reset' was run."""
import secrets
import unicodedata

from common import get_mysql_connection


TABLES = {
    "users",
    "genre",
    "book",
    "reading_record",
    "favorite_genre",
    "community_post",
    "post_comment",
}

NEW_TABLES = (
    """CREATE TABLE IF NOT EXISTS profile_pictures(
  user_id       INT PRIMARY KEY,
  data          MEDIUMBLOB NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
)""",
    """CREATE TABLE IF NOT EXISTS follows (
        follower_id INT NOT NULL,
        followee_id INT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (follower_id, followee_id),
        FOREIGN KEY (follower_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (followee_id) REFERENCES users(user_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS post_type (
        type_id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(63) NOT NULL UNIQUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS post_extra (
        post_id INT PRIMARY KEY,
        isbn VARCHAR(13) NULL,
        quote TEXT NULL,
        spoiler_stage ENUM('EARLY','MID','LATE') NULL,
        rating TINYINT NULL CHECK (rating BETWEEN 1 AND 5),
        recommend_verdict ENUM('RECOMMEND','NOT_RECOMMEND') NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES community_post(post_id) ON DELETE CASCADE,
        FOREIGN KEY (isbn) REFERENCES book(isbn)
    )""",
    """CREATE TABLE IF NOT EXISTS media (
        media_id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        post_id INT NULL,
        data MEDIUMBLOB NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (post_id) REFERENCES community_post(post_id) ON DELETE SET NULL
    )""",
    """CREATE TABLE IF NOT EXISTS polls (
        poll_id INT AUTO_INCREMENT PRIMARY KEY,
        post_id INT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES community_post(post_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS poll_options (
        option_id INT AUTO_INCREMENT PRIMARY KEY,
        poll_id INT NOT NULL,
        label VARCHAR(255) NOT NULL,
        position INT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (poll_id) REFERENCES polls(poll_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS poll_votes (
        user_id INT NOT NULL,
        poll_id INT NOT NULL,
        option_id INT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, option_id, poll_id),
        FOREIGN KEY (poll_id) REFERENCES polls(poll_id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (option_id) REFERENCES poll_options(option_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS post_like (
        user_id INT NOT NULL,
        post_id INT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, post_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (post_id) REFERENCES community_post(post_id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS comment_reaction (
  comment_id        INT NOT NULL,
  user_id           INT NOT NULL,
  reaction          ENUM('LIKE','DISLIKE') NOT NULL,
  created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (comment_id, user_id),
  FOREIGN KEY (comment_id)        REFERENCES post_comment(comment_id) ON DELETE CASCADE,
  FOREIGN KEY (user_id)           REFERENCES users(user_id) ON DELETE CASCADE
)"""
)


def existing_tables(cursor):
    cursor.execute("SHOW TABLES")
    return {next(iter(row.values())) for row in cursor.fetchall()}


def has_column(cursor, table, column):
    cursor.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
    return cursor.fetchone() is not None


def ensure_media_data_capacity(cursor):
    cursor.execute("SHOW COLUMNS FROM `media` LIKE %s", ("data",))
    column = cursor.fetchone()
    if not column:
        raise RuntimeError("The media.data column is missing.")
    data_type = column["Type"].lower()
    if data_type not in ("mediumblob", "longblob"):
        cursor.execute("ALTER TABLE media MODIFY COLUMN data MEDIUMBLOB NOT NULL")


def has_unique_index(cursor, table, column):
    cursor.execute(f"SHOW INDEX FROM `{table}`")
    indexes = {}
    for row in cursor.fetchall():
        indexes.setdefault(row["Key_name"], []).append(row)
    return any(
        len(rows) == 1
        and rows[0]["Non_unique"] == 0
        and rows[0]["Column_name"] == column
        for rows in indexes.values()
    )


def has_foreign_key(cursor, table, column, referenced_table, referenced_column):
    cursor.execute(
        """SELECT 1 FROM information_schema.KEY_COLUMN_USAGE
           WHERE TABLE_SCHEMA = DATABASE()
             AND TABLE_NAME = %s
             AND COLUMN_NAME = %s
             AND REFERENCED_TABLE_NAME = %s
             AND REFERENCED_COLUMN_NAME = %s
           LIMIT 1""",
        (table, column, referenced_table, referenced_column),
    )
    return cursor.fetchone() is not None


def nickname_key_for(cursor, nickname, user_id, used):
    base = unicodedata.normalize("NFKC", nickname or "").strip().casefold()
    if not base:
        base = f"reader-{user_id}"
    candidate = base[:32]

    def collides(value):
        cursor.execute(
            """SELECT 1 FROM users
               WHERE nickname_key = %s AND user_id <> %s
               LIMIT 1""",
            (value, user_id),
        )
        return value.casefold() in used or cursor.fetchone() is not None

    if collides(candidate):
        suffix = f"-{user_id}"
        candidate = base[: 32 - len(suffix)] + suffix
    while collides(candidate):
        suffix = "-" + secrets.token_hex(4)
        candidate = base[: 32 - len(suffix)] + suffix
    return candidate


def migrate_users(cursor):
    if not has_column(cursor, "users", "public_id"):
        cursor.execute("ALTER TABLE users ADD COLUMN public_id VARCHAR(32) NULL")
    if not has_column(cursor, "users", "nickname_key"):
        cursor.execute("ALTER TABLE users ADD COLUMN nickname_key VARCHAR(32) NULL")
    if not has_column(cursor, "users", "onboarded"):
        cursor.execute(
            "ALTER TABLE users ADD COLUMN onboarded BOOLEAN NOT NULL DEFAULT FALSE"
        )

    cursor.execute(
        "SELECT user_id, nickname, public_id, nickname_key FROM users ORDER BY user_id"
    )
    users = cursor.fetchall()
    used_public_ids = {row["public_id"] for row in users if row["public_id"]}
    used_nickname_keys = {
        row["nickname_key"].casefold() for row in users if row["nickname_key"]
    }

    for row in users:
        public_id = row["public_id"]
        while not public_id:
            candidate = secrets.token_hex(16)
            if candidate not in used_public_ids:
                public_id = candidate
                used_public_ids.add(public_id)

        nickname_key = row["nickname_key"]
        if not nickname_key:
            nickname_key = nickname_key_for(
                cursor, row["nickname"], row["user_id"], used_nickname_keys
            )
            used_nickname_keys.add(nickname_key.casefold())

        if public_id != row["public_id"] or nickname_key != row["nickname_key"]:
            cursor.execute(
                "UPDATE users SET public_id = %s, nickname_key = %s WHERE user_id = %s",
                (public_id, nickname_key, row["user_id"]),
            )

    for column, index_name in (
        ("public_id", "uq_users_public_id"),
        ("nickname_key", "uq_users_nickname_key"),
    ):
        if not has_unique_index(cursor, "users", column):
            cursor.execute(
                f"ALTER TABLE users ADD UNIQUE KEY `{index_name}` (`{column}`)"
            )
        cursor.execute(
            f"ALTER TABLE users MODIFY `{column}` VARCHAR(32) NOT NULL"
        )


def migrate_columns(cursor):
    columns = (
        ("reading_record", "progress",
         "ENUM('EARLY','MID','LATE') NULL AFTER end_date"),
        ("community_post", "post_type_id", "INT NULL AFTER category_id"),
        ("community_post", "has_spoiler",
         "BOOLEAN NOT NULL DEFAULT FALSE AFTER is_announcement"),
        ("community_post", "anonymous",
         "BOOLEAN NOT NULL DEFAULT FALSE AFTER has_spoiler"),
        ("post_comment", "anonymous",
         "BOOLEAN NOT NULL DEFAULT FALSE AFTER dislike_count"),
        ("post_comment", "deleted",
         "BOOLEAN NOT NULL DEFAULT FALSE AFTER anonymous"),
    )
    for table, column, definition in columns:
        if not has_column(cursor, table, column):
            cursor.execute(
                f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}"
            )

    if not has_column(cursor, "favorite_genre", "preference"):
        cursor.execute(
            """ALTER TABLE favorite_genre
               ADD COLUMN preference ENUM('LIKE','DISLIKE') NULL"""
        )
    cursor.execute(
        "UPDATE favorite_genre SET preference = 'LIKE' WHERE preference IS NULL"
    )
    cursor.execute(
        """ALTER TABLE favorite_genre
           MODIFY preference ENUM('LIKE','DISLIKE') NOT NULL"""
    )


def migrate_post_type(cursor):
    cursor.execute("INSERT IGNORE INTO post_type (name) VALUES ('legacy')")
    cursor.execute("SELECT type_id FROM post_type WHERE name = 'legacy'")
    legacy_type_id = cursor.fetchone()["type_id"]
    cursor.execute(
        "UPDATE community_post SET post_type_id = %s WHERE post_type_id IS NULL",
        (legacy_type_id,),
    )
    cursor.execute(
        "ALTER TABLE community_post MODIFY post_type_id INT NOT NULL"
    )
    if not has_foreign_key(
        cursor, "community_post", "post_type_id", "post_type", "type_id"
    ):
        cursor.execute(
            """ALTER TABLE community_post
               ADD CONSTRAINT fk_community_post_post_type
               FOREIGN KEY (post_type_id) REFERENCES post_type(type_id)"""
        )


def migrate():
    connection = get_mysql_connection()
    try:
        with connection.cursor() as cursor:
            tables = existing_tables(cursor)
            missing = TABLES - tables
            if missing:
                raise RuntimeError(
                    "Initialize the database first; required tables are missing: "
                    + ", ".join(sorted(missing))
                )

            migrate_users(cursor)
            migrate_columns(cursor)
            cursor.execute(NEW_TABLES[0])
            cursor.execute(NEW_TABLES[1])
            migrate_post_type(cursor)
            for statement in NEW_TABLES[2:]:
                cursor.execute(statement)
            ensure_media_data_capacity(cursor)
        connection.commit()
        print("MySQL schema update complete.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    migrate()
