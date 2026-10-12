import { useState } from "react";
import { Link } from "react-router-dom";
import { useLibrary } from "../components/LibraryContext";
import { Cover } from "../components/BookCard";
import Modal from "../components/Modal";
import ReadingCalendar from "../components/ReadingCalendar";
import { useAuth } from "../components/AuthContext";
const states = {
  ALL: "전체",
  WISH: "읽을 예정",
  READING: "읽는 중",
  COMPLETED: "완독",
};
export default function LibraryPage() {
  const { user, loading: authLoading, error } = useAuth();
  const { records, update, remove, notice, busy, loading } = useLibrary(),
    [filter, setFilter] = useState("ALL"),
    [selected, setSelected] = useState(null);
  const record = records.find((x) => x.id === selected);
  const completed = records.filter((x) => x.status === "COMPLETED").length;
  async function edit(e) {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      startDate = String(f.get("startDate")),
      endDate = String(f.get("endDate"));
    if (startDate && endDate && endDate < startDate) {
      e.currentTarget
        .querySelector("[name=endDate]")
        .setCustomValidity("완독일은 시작일 이후로 선택해주세요.");
      e.currentTarget.reportValidity();
      return;
    }
    if (
      await update(selected, {
        status: String(f.get("status")),
        startDate,
        endDate,
        rating: Number(f.get("rating")),
        review: String(f.get("review")),
      })
    )
      setSelected(null);
  }
  if (authLoading)
    return (
      <main className="container workspace-page">
        <p role="status">로그인 확인 중…</p>
      </main>
    );
  if (!user)
    return (
      <main className="container workspace-page">
        <div className="empty-state">
          <h1>나만의 서재</h1>
          <p>로그인하고 읽고 싶은 책과 독서 기록을 모아보세요.</p>
          {error && <p role="alert">{error}</p>}
          <Link className="primary-btn" to="/login">
            로그인하기
          </Link>
          <Link className="outline-btn" to="/search">
            책 둘러보기
          </Link>
        </div>
      </main>
    );
  if (loading)
    return (
      <main className="container workspace-page">
        <p role="status">서재를 불러오는 중…</p>
      </main>
    );
  return (
    <main className="container workspace-page library-page">
      <div className="page-top">
        <div>
          <p className="section-kicker">MY READING SPACE</p>
          <h1>내 서재</h1>
          <p className="page-subtitle">
            읽고 싶은 책부터 기억하고 싶은 한 문장까지.
          </p>
        </div>
        <Link className="primary-btn" to="/search">
          책 담으러 가기
        </Link>
      </div>
      <div className="library-summary">
        {[
          ["서재의 책", records.length],
          ["읽는 중", records.filter((x) => x.status === "READING").length],
          ["완독한 책", completed],
        ].map(([title, count]) => (
          <div key={title}>
            <span>{title}</span>
            <strong>
              {count}
              <small>권</small>
            </strong>
          </div>
        ))}
      </div>
      <p className="local-notice">
        서재와 달력 기록은 로그인한 계정별로 이 브라우저에 저장돼요.
      </p>
      <ReadingCalendar />
      <div className="library-tabs">
        {Object.entries(states).map(([value, label]) => (
          <button
            key={value}
            aria-pressed={filter === value}
            onClick={() => setFilter(value)}
          >
            {label}{" "}
            <span>
              {value === "ALL"
                ? records.length
                : records.filter((x) => x.status === value).length}
            </span>
          </button>
        ))}
      </div>
      <p role="status" className="local-status">
        {notice}
      </p>
      {records.filter((x) => filter === "ALL" || x.status === filter).length ? (
        <div className="shelf-grid">
          {records
            .filter((x) => filter === "ALL" || x.status === filter)
            .map((r) => (
              <article className="shelf-book" key={r.id}>
                <button
                  className="shelf-cover"
                  onClick={() => setSelected(r.id)}
                  aria-label={`${r.book.title} 독서 기록 편집`}
                >
                  <Cover book={r.book} />
                </button>
                <div className="shelf-info">
                  <span className={"status-badge status-" + r.status}>
                    {states[r.status]}
                  </span>
                  <h3>{r.book.title}</h3>
                  <p>{r.book.author}</p>
                  {r.rating > 0 && (
                    <p className="stars">
                      {"★".repeat(r.rating)}
                      {"☆".repeat(5 - r.rating)}
                    </p>
                  )}
                  <button
                    className="text-btn"
                    onClick={() => setSelected(r.id)}
                  >
                    독서 기록 편집 →
                  </button>
                </div>
              </article>
            ))}
        </div>
      ) : (
        <div className="empty-state">
          <h2>아직 이 칸에 담긴 책이 없어요</h2>
          <p>검색 결과에서 ‘내 서재에 담기’를 눌러 시작해보세요.</p>
          <Link to="/search" className="primary-btn">
            책 검색하기
          </Link>
        </div>
      )}
      <Modal open={!!record} close={() => setSelected(null)} title="독서 기록">
        {record && (
          <form key={record.id} className="editor-form" onSubmit={edit}>
            <h3>{record.book.title}</h3>
            <label>
              독서 상태
              <select name="status" defaultValue={record.status}>
                {Object.entries(states)
                  .filter(([v]) => v !== "ALL")
                  .map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
              </select>
            </label>
            <div className="date-fields">
              <label>
                시작일
                <input
                  name="startDate"
                  type="date"
                  defaultValue={record.startDate}
                />
              </label>
              <label>
                완독일
                <input
                  name="endDate"
                  type="date"
                  defaultValue={record.endDate}
                  onChange={(e) => e.target.setCustomValidity("")}
                />
              </label>
            </div>
            <label>
              별점
              <select name="rating" defaultValue={record.rating}>
                {[0, 1, 2, 3, 4, 5].map((v) => (
                  <option key={v} value={v}>
                    {v ? "★".repeat(v) : "평가 전"}
                  </option>
                ))}
              </select>
            </label>
            <label>
              감상평
              <textarea
                name="review"
                rows={4}
                defaultValue={record.review}
                maxLength={3000}
              />
            </label>
            <button className="primary-btn" disabled={busy}>
              기록 저장
            </button>
            <button
              type="button"
              className="danger-btn"
              onClick={async () => {
                if (window.confirm("이 책을 서재에서 삭제할까요?")) {
                  if (await remove(record.id)) setSelected(null);
                }
              }}
            >
              서재에서 삭제
            </button>
            <p role="status">{notice}</p>
          </form>
        )}
      </Modal>
    </main>
  );
}
