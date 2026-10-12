import { useState } from "react";
import { useLibrary } from "./LibraryContext";
export function safeURL(value) {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
export function Cover({ book }) {
  const [failed, setFailed] = useState(false),
    url = safeURL(book.cover_image_url);
  return (
    <div className="result-cover">
      {url && !failed ? (
        <img
          src={url}
          alt={`${book.title} 표지`}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      ) : (
        <strong>{book.title || "제목 정보 없음"}</strong>
      )}
    </div>
  );
}
export default function BookCard({ book }) {
  const { records, add, notice, busy } = useLibrary();
  const exists = records.some(
      (item) => item.id === String(book.isbn || `${book.title}|${book.author}`),
    ),
    [clicked, setClicked] = useState(false);
  return (
    <article className="result-card">
      <Cover book={book} />
      <div className="result-info">
        <h3>{book.title}</h3>
        <p>{book.author || "저자 정보 없음"}</p>
        {(book.publisher || book.publish_year) && (
          <p>
            {[book.publisher, book.publish_year].filter(Boolean).join(" · ")}
          </p>
        )}
        {book.isbn && <p>ISBN {book.isbn}</p>}
        {book.description && <p className="description">{book.description}</p>}
        <button
          className="outline-btn"
          disabled={exists || busy}
          onClick={() => {
            add(book);
            setClicked(true);
          }}
        >
          {exists ? "서재에 담았어요" : "내 서재에 담기"}
        </button>
        {clicked && <p role="status">{notice}</p>}
      </div>
    </article>
  );
}
