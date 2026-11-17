import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useLibrary } from "../components/LibraryContext";
import BookCard from "../components/BookCard";
import Modal from "../components/Modal";
import OneLineReviewList from "../components/OneLineReviewList";
import ReadingCalendar from "../components/ReadingCalendar";
import { useAuth } from "../components/AuthContext";
const states = {
  ALL: "전체",
  WISH: "읽을 예정",
  READING: "읽는 중",
  COMPLETED: "완독",
};
export default function LibraryPage() {
  const [params] = useSearchParams();
  const { user, loading: authLoading, error } = useAuth();
  const { records, update, remove, notice, busy, loading } = useLibrary(),
    [filter, setFilter] = useState("ALL"),
    [selected, setSelected] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ status: "WISH", startDate: "", endDate: "" });
  const record = records.find((x) => x.id === selected);
  function reviewCard(item) {
    return <OneLineReviewList lines={[{
      id: item.id, body: item.review, rating: item.rating,
      hasSpoiler: !!item.hasSpoiler,
      author: { nickname: user.nickname || "독자" },
    }]} />;
  }
  const completed = records.filter((x) => x.status === "COMPLETED").length;
  function startEditing() {
    setDraft({
      status: record.status,
      startDate: record.status === "WISH" ? "" : record.startDate || "",
      endDate: record.status === "WISH" ? "" : record.endDate || "",
    });
    setEditing(true);
  }
  async function edit(e) {
    e.preventDefault();
    const f = new FormData(e.currentTarget),
      startDate = draft.status === "WISH" ? "" : String(f.get("startDate") || ""),
      endDate = draft.status === "WISH" ? "" : String(f.get("endDate") || "");
    if (startDate && endDate && endDate < startDate) {
      e.currentTarget
        .querySelector("[name=endDate]")
        .setCustomValidity("완독일은 시작일 이후로 선택해주세요.");
      e.currentTarget.reportValidity();
      return;
    }
    const updated = await update(selected, {
      status: String(f.get("status")),
      startDate,
      endDate,
    });
    if (updated)
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

          <h1>내 서재</h1>

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

      <ReadingCalendar initialDate={params.get("date")} />
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
                <BookCard book={r.book} showDescription={false} />
                <div className="shelf-info">
                  <span className={"status-badge status-" + r.status}>
                    {states[r.status]}
                  </span>
                  {!r.review && r.rating > 0 && (
                    <p className="stars">
                      {"★".repeat(r.rating)}
                      {"☆".repeat(5 - r.rating)}
                    </p>
                  )}
                  {r.review && reviewCard(r)}
                  <button
                    className="text-btn"
                    onClick={() => { setSelected(r.id); setEditing(false); }}
                  >
                    독서 기록 보기 →
                  </button>
                </div>
              </article>
            ))}
        </div>
      ) : (
        <div className="empty-state">
          <h2>아직 이 칸에 담긴 책이 없어요</h2>

          <Link to="/search" className="primary-btn">
            책 검색하기
          </Link>
        </div>
      )}
      <Modal open={!!record} close={() => setSelected(null)} title="독서 기록">
        {record && (!editing ? <section className="memo-preview"><h3>{record.book.title}</h3><p>{states[record.status]}{!record.review && (record.rating ? ' · ' + '★'.repeat(record.rating) : ' · 평가 전')}</p>{record.status !== 'WISH' && <p>시작일 {record.startDate || '미등록'} · 완독일 {record.endDate || '미등록'}</p>}{record.review ? reviewCard(record) : <p>아직 작성한 한줄평이 없어요.</p>}<button type="button" className="primary-btn" onClick={startEditing}>독서 기록 수정</button></section> : (
          <form key={record.id} className="editor-form" onSubmit={edit}
            onChange={(event) => event.currentTarget.elements.endDate?.setCustomValidity("")}>
            <h3>{record.book.title}</h3>
            <label>
              독서 상태
              <select name="status" value={draft.status} disabled={busy}
                onChange={(event) => {
                  const status = event.target.value;
                  setDraft(current => status === "WISH"
                    ? { status, startDate: "", endDate: "" } : { ...current, status });
                }}>
                {Object.entries(states)
                  .filter(([v]) => v !== "ALL")
                  .map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
              </select>
            </label>
            {draft.status !== "WISH" && <div className="date-fields">
              <label>
                시작일
                <input
                  name="startDate"
                  type="date"
                  value={draft.startDate}
                  disabled={draft.status === "WISH" || busy}
                  onChange={(event) => setDraft(current => ({ ...current, startDate: event.target.value }))}
                />
              </label>
              <label>
                완독일
                <input
                  name="endDate"
                  type="date"
                  value={draft.endDate}
                  min={draft.startDate || undefined}
                  disabled={draft.status === "WISH" || busy}
                  onChange={(event) => setDraft(current => ({ ...current, endDate: event.target.value }))}
                />
              </label>
            </div>}
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
            <button type="button" className="text-btn" disabled={busy} onClick={() => setEditing(false)}>수정 취소</button>
          </form>
        ))}
      </Modal>
    </main>
  );
}
