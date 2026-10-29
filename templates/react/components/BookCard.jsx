import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useLibrary } from "./LibraryContext";
import { useAuth } from "./AuthContext";
import { getBookDetail } from "../api";
import Modal from "./Modal";
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
  const { records, add, update, notice, busy } = useLibrary();
  const { user } = useAuth();
  const record = records.find((item) => item.id === String(book.isbn || `${book.title}|${book.author}`));
  const [open, setOpen] = useState(false), [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false), [error, setError] = useState("");
  const [retry, setRetry] = useState(0), [clicked, setClicked] = useState(false);
  const [reviewMessage, setReviewMessage] = useState("");
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
  const info = { ...book, ...detail, description: detail?.description || book.description || "" };
  const description = info.description;
  async function saveReview(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setReviewMessage("");
    if (await update(record.id, { rating: Number(form.get("rating")), review: String(form.get("review")).trim() }))
      setReviewMessage("평점과 코멘트를 저장했어요.");
  }
  const addButton = (
    <>
      <button type="button" className="primary-btn" disabled={!!record || busy}
        onClick={() => { add(info); setClicked(true); }}>
        {record ? "서재에 담았어요" : busy ? "저장 중…" : "내 서재에 담기"}
      </button>
      {clicked && <p role="status">{notice}</p>}
      {!user && <p><Link to="/login">로그인</Link> 후 서재에 담을 수 있어요.</p>}
    </>
  );
  return (
    <article className="result-card" id={book.isbn ? `book-${book.isbn}` : undefined}>
      <button className="book-cover-button" type="button" onClick={() => setOpen(true)}
        aria-label={`${book.title} 상세정보`} aria-haspopup="dialog"><Cover book={book} /></button>
      <div className="result-info">
        <h3><button type="button" className="book-title-button" onClick={() => setOpen(true)}
          aria-haspopup="dialog">{book.title}</button></h3>
        {record && <span className="shelf-badge">✓ 내 서재에 담긴 책</span>}
        <p>{book.author || "저자 정보 없음"}</p>
        {book.match?.length > 0 && <ul className="match-tags" aria-label="추천 이유">
          {book.match.map((m) => <li key={m}>{matchLabels[m] || m}</li>)}
        </ul>}
        {(book.publisher || book.publish_year) && <p>{[book.publisher, book.publish_year].filter(Boolean).join(" · ")}</p>}
        {showDescription && <p className="description">{description || (loading ? "줄거리를 불러오는 중…" : error ? "줄거리를 불러오지 못했어요. 상세정보에서 다시 시도해주세요." : "제공된 줄거리가 없어요.")}</p>}
        <button type="button" className="outline-btn" onClick={() => setOpen(true)} aria-haspopup="dialog">상세정보 보기</button>
      </div>
      <Modal open={open} close={() => { setOpen(false); setClicked(false); setReviewMessage(""); }} title="도서 상세정보">
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
            ? `★ ${Number(info.average_rating).toFixed(1)} / 5 · 리뷰 ${info.review_count}개` : "아직 등록된 평점이 없어요."}</p></section>
          <section><h3>코멘트</h3>{info.reviews?.length ? info.reviews.map((review, i) => <article className="book-review" key={i}>
            <strong>{review.nickname || "독자"}</strong><span> · {"★".repeat(Math.max(0, Math.min(5, Number(review.rating) || 0)))}</span>
            {review.has_spoiler ? <details><summary>스포일러가 포함된 코멘트 보기</summary><p>{review.content || "작성된 코멘트가 없어요."}</p></details>
              : <p>{review.content || "작성된 코멘트가 없어요."}</p>}
          </article>) : <p>아직 등록된 코멘트가 없어요.</p>}</section>
          {record && <section><h3>내 평점과 코멘트</h3>
            <form key={record.id} className="editor-form" onSubmit={saveReview}>
              <label>내 평점<select name="rating" defaultValue={record.rating || 0}>
                {[0, 1, 2, 3, 4, 5].map((v) => <option key={v} value={v}>{v ? "★".repeat(v) : "평가 전"}</option>)}
              </select></label>
              <label>내 코멘트<textarea name="review" rows={3} maxLength={3000} defaultValue={record.review || ""} /></label>
              <button className="outline-btn" disabled={busy}>평점·코멘트 저장</button>
              <small>내 기록은 로그인한 계정의 서재에 저장돼요.</small>
              <p role="status">{reviewMessage || notice}</p>
            </form>
          </section>}
          <div className="book-detail-actions">{addButton}</div>
        </div>}
      </Modal>
    </article>
  );
}
