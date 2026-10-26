"""Select result cards mentioned in the ORIGINAL commentary; never rewrite it."""
import re
import unicodedata

from common import get_mysql_connection
from routers.books import CARD_COLUMNS, search_books


def normalized(value):
    return re.sub(r"[^\w가-힣]", "", unicodedata.normalize("NFC", value or "")).casefold()


def names_in_comment(comment):
    quoted = re.findall(r"『([^』\n]{1,150})』|《([^》\n]{1,150})》|「([^」\n]{1,150})」|\*\*([^*\n]{1,150})\*\*", comment)
    names, seen = [], set()
    for parts in quoted:
        title = next((part.strip() for part in parts if part), "")
        key = normalized(title)
        if key and key not in seen:
            names.append(title)
            seen.add(key)
    return names[:10]


def mentioned(book, comment):
    title = book.get("title") or ""
    aliases = [title]
    # A generated comment may omit the subtitle, but not the main title.
    main_title = re.split(r"[:：]", title, maxsplit=1)[0].strip()
    if len(normalized(main_title)) >= 2:
        aliases.append(main_title)
    for alias in aliases:
        compact = normalized(alias)
        if not compact:
            continue
        for quoted in names_in_comment(comment):
            if normalized(quoted) == compact:
                return True
        # Plain titles with optional spaces and Korean particles.
        pattern = r"\s*".join(re.escape(char) for char in alias if not char.isspace())
        if not pattern:
            continue
        tail = r"(?=$|[^\w가-힣]|(?:은|는|을|를|이|가|과|와|의|도|에서|처럼|입니다)(?=$|\s|[^\w가-힣]))"
        if re.search(r"(?<![\w가-힣])" + pattern + tail, comment, flags=re.IGNORECASE):
            return True
    return False


def resolve_title(title):
    """Read-only lookup for a quoted title outside the initial candidates."""
    key = normalized(title)
    conn = get_mysql_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT {CARD_COLUMNS} FROM book WHERE title = %s OR REPLACE(title, ' ', '') = %s LIMIT 10",
                           (title, title.replace(" ", "")))
            rows = cursor.fetchall()
    finally:
        conn.close()
    exact = next((book for book in rows if normalized(book.get("title")) == key), None)
    if exact:
        return exact
    result = search_books(q=title, by="title", page=1, size=20)
    return next((book for book in result["books"] if normalized(book.get("title")) == key), None)


def filter_comment_books(result):
    comment = result.get("ai_comment")
    if not isinstance(comment, str) or not comment.strip():
        return result
    candidates = [*result.get("books", []), *result.get("same_author", [])]
    selected, seen = [], set()
    for book in candidates:
        key = str(book.get("isbn") or normalized(book.get("title")))
        if key not in seen and mentioned(book, comment):
            selected.append(book)
            seen.add(key)
    unresolved = []
    for title in names_in_comment(comment):
        if any(mentioned(book, f"『{title}』") for book in selected):
            continue
        try:
            book = resolve_title(title)
        except Exception:
            book = None  # No fabricated cards and no changes to the comment.
        if book:
            key = str(book.get("isbn") or normalized(book.get("title")))
            if key not in seen:
                selected.append(book)
                seen.add(key)
        else:
            unresolved.append(title)
    return {**result, "books": selected, "same_author": [],
            "unmatched_comment_titles": unresolved,
            "comment_books_message": ("코멘트에 언급된 도서 정보를 찾지 못했어요." if not selected else
                                      "코멘트에 언급된 일부 도서 정보를 찾지 못했어요." if unresolved else None)}
