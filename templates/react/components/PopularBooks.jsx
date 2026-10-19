import { useEffect, useState } from "react";
import { request } from "../api";
import BookCard from "./BookCard";
export default function PopularBooks() {
  const [data, setData] = useState(null),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    setData(null);
    request("/api/books/popular", { signal: controller.signal })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [retry]);
  return (
    <section className="popular-books">
      <h2>요즘 많이 읽는 책</h2>
      <p className="page-subtitle">
        정보나루 · 최근 30일 인기 대출 도서
        {data && ` (${data.start} ~ ${data.end})`}
      </p>
      {error ? (
        <p role="status">
          {error}{" "}
          <button className="text-btn" onClick={() => setRetry((x) => x + 1)}>
            다시 시도
          </button>
        </p>
      ) : !data ? (
        <p role="status">인기 도서를 불러오는 중…</p>
      ) : data.books.length ? (
        <div className="popular-grid">
          {data.books.map((book, i) => (
            <div key={book.isbn || i}>
              <span className="popular-rank">{book.ranking || i + 1}위</span>
              <BookCard book={book} showDescription={false} />
            </div>
          ))}
        </div>
      ) : (
        <p>해당 기간의 인기 도서가 없어요.</p>
      )}
    </section>
  );
}
