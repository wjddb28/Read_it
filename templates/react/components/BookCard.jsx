import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useLibrary } from "./LibraryContext";
import { useAuth } from "./AuthContext";
import { getBookDetail, invalidateBookDetail, request } from "../api";
import BookDiscussion from "./BookDiscussion";
import Modal from "./Modal";
import BookOneLineReviews from "./BookOneLineReviews";
export function safeURL(value) {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.origin);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
// '○○와 비슷한 책' 추천 이유 (백엔드 routers/similar.py 의 match 값)
const matchLabels = { 줄거리: "줄거리 비슷", 장르: "같은 장르", "함께 대출": "함께 많이 빌린 책" };
export function Cover({ book }) {
  const [failed, setFailed] = useState(false), url = safeURL(book.cover_image_url);
  useEffect(() => setFailed(false), [url]);
  return (
    <div className="result-cover">
      {url && !failed ? <img src={url} alt={`${book.title} 표지`} loading="lazy"
        referrerPolicy="no-referrer" onError={() => setFailed(true)} />
        : <strong>{book.title || "제목 정보 없음"}</strong>}
    </div>
  );
}

export default function BookCard({ book, showDescription = true }) {
  const {
    records,
    add,
    notice,
    busy,
  } = useLibrary();
  const { user } = useAuth();
  const record = records.find((item) => item.id === String(book.isbn || `${book.title}|${book.author}`));
  const [open, setOpen] = useState(false), [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false), [error, setError] = useState("");
  const [retry, setRetry] = useState(0), [clicked, setClicked] = useState(false);
  function openDetails() {
    if (book.isbn) invalidateBookDetail(book.isbn);
    setOpen(true);
  }
  useEffect(() => {
    if (!book.isbn || (!open && (!showDescription || book.description))) return;
    let active = true;
    setLoading(true);
    setError("");
    getBookDetail(book.isbn).then((data) => {
      if (active) setDetail(data);
    }).catch((e) => {
      if (active) setError(e.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [book.isbn, book.description, open, retry, showDescription]);
  useEffect(() => {
    if (!open || !user || !book.isbn || !detail?.reviews?.length) return;
    let active = true;
    setReactionsLoaded(false);
    request(`/api/library/review/${encodeURIComponent(book.isbn)}/reactions`)
      .then(({ reactions }) => {
        if (active) {
          setReviewReactions(Object.fromEntries(
            reactions.map((reaction) => [reaction.review_id, reaction]),
          ));
          setReactionsLoaded(true);
          setReactionError("");
        }
      })
      .catch((e) => {
        if (active) setReactionError(e.message);
      });
    return () => { active = false; };
  }, [book.isbn, detail?.reviews, open, user]);
  const info = { ...book, ...detail, description: detail?.description || book.description || "" };
  const description = info.description;
  const addButton = (
    <>
      <button type="button" className="primary-btn" disabled={!!record || busy}
        onClick={() => { add(info); setClicked(true); }}>
        {record ? "서재에 담았어요" : busy ? "저장 중…" : "내 서재에 담기"}
      </button>
      {clicked && <p role="status">{notice}</p>}
      {!user && <p><Link to="/login">로그인</Link>이 필요해요.</p>}
    </>
  );
  return (
    <article className="result-card" id={book.isbn ? `book-${book.isbn}` : undefined}>
      <button className="book-cover-button" type="button" onClick={openDetails}
        aria-label={`${book.title} 상세정보`} aria-haspopup="dialog"><Cover book={book} /></button>
      <div className="result-info">
        <h3><button type="button" className="book-title-button" onClick={openDetails}
          aria-haspopup="dialog">{book.title}</button></h3>
        {record && <span className="shelf-badge">✓ 내 서재에 담긴 책</span>}
        <p>{book.author || "저자 정보 없음"}</p>
        {book.match?.length > 0 && <ul className="match-tags" aria-label="추천 이유">
          {book.match.map((m) => <li key={m}>{matchLabels[m] || m}</li>)}
        </ul>}
        {(book.publisher || book.publish_year) && <p>{[book.publisher, book.publish_year].filter(Boolean).join(" · ")}</p>}
        {showDescription && <p className="description">{description || (loading ? "줄거리를 불러오는 중…" : error ? "줄거리를 불러오지 못했어요. 상세정보에서 다시 시도해주세요." : "제공된 줄거리가 없어요.")}</p>}
        <button type="button" className="outline-btn" onClick={openDetails} aria-haspopup="dialog">상세정보 보기</button>

      </div>
      <Modal open={open} close={() => { setOpen(false); setClicked(false); }} title="도서 상세정보" size="wide">
        {open && <div className="book-detail">
          <div className="book-detail-heading"><Cover book={info} /><div>
            <h3>{info.title}</h3><p>{info.author || "저자 정보 없음"}</p>
            <p>{[info.publisher, info.publish_year].filter(Boolean).join(" · ")}</p>
            {info.isbn && <small>ISBN {info.isbn}</small>}
          </div></div>
          {loading && <p role="status">상세정보를 불러오는 중…</p>}
          {error && <p role="alert">{error} <button type="button" className="text-btn" onClick={() => setRetry((n) => n + 1)}>다시 시도</button></p>}
          <section><h3>줄거리</h3><p className="book-detail-description">{description || "제공된 줄거리가 없어요."}</p></section>
          <section><h3>키워드</h3>{info.keywords?.length ? <ul className="match-tags">{info.keywords.map((keyword) => {
            const word = typeof keyword === "string" ? keyword : keyword.word;
            return <li key={word}>{word}</li>;
          })}</ul> : <p>등록된 키워드가 없어요.</p>}</section>
          <section><h3>평점</h3><p>{Number(info.review_count) > 0 && info.average_rating != null
            ? `★ ${Number(info.average_rating).toFixed(1)} / 5 · 평점 ${info.review_count}개` : "아직 등록된 평점이 없어요."}</p></section>
          {info.isbn && <BookOneLineReviews book={info} onSaved={() => setRetry(n => n + 1)} />}
          <BookDiscussion book={info} />
          <div className="book-detail-actions">{addButton}</div>
        </div>}
      </Modal>
    </article>
  );
}
