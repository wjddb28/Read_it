import { useEffect, useState } from "react";
import { useLibrary } from "./LibraryContext";
import { Cover } from "./BookCard";
import Modal from "./Modal";
import { dateFromKey, hasMemo } from "../readingDates";
import "../../../static/css/react/calendar.css";

function dateKey(year, month, day) {
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export default function ReadingCalendar({ initialDate }) {
  const { records, updateLog, busy, notice } = useLibrary();
  const today = new Date();
  const todayKey = dateKey(
    today.getFullYear(),
    today.getMonth(),
    today.getDate(),
  );
  const [month, setMonth] = useState(
    () => new Date(today.getFullYear(), today.getMonth(), 1),
  );
  const [completedOnly, setCompletedOnly] = useState(false);
  const [selected, setSelected] = useState(null);
  const [bookId, setBookId] = useState("");
  const [saved, setSaved] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const year = month.getFullYear();
  const index = month.getMonth();
  const offset = new Date(year, index, 1).getDay();
  const days = new Date(year, index + 1, 0).getDate();
  const book = records.find((record) => record.id === bookId) || entriesOn(selected, false)[0] || records[0];

  function entriesOn(date, filter = completedOnly) {
    return records.filter((record) =>
      filter
        ? record.status === "COMPLETED" && record.endDate === date
        : record.startDate === date || record.endDate === date || hasMemo(record, date),
    );
  }

  useEffect(() => {
    const date = dateFromKey(initialDate);
    if (date) {
      setMonth(new Date(date.getFullYear(), date.getMonth(), 1));
      setSelected(initialDate); setBookId(""); setSaved("");
    }
  }, [initialDate]);

  function openDate(date) {
    setSelected(date);
    setBookId(entriesOn(date)[0]?.id || records[0]?.id || "");
    setSaved("");
  }

  async function save(event) {
    event.preventDefault();
    if (!book || !selected) return;
    setSaved("");
    const memo = String(new FormData(event.currentTarget).get("memo")).trim();
    if (!memo) {
      if (hasMemo(book, selected)) setDeleteTarget({ id: book.id, date: selected });
      else setSaved("독서 메모를 입력해주세요.");
      return;
    }
    if (await updateLog(book.id, selected, memo)) setSaved("이 날짜의 독서 메모를 저장했어요.");
  }

  async function deleteMemo() {
    if (!deleteTarget) return;
    const { id, date } = deleteTarget;
    if (await updateLog(id, date, null)) {
      setDeleteTarget(null); setSaved("메모를 삭제했어요.");
    }
  }

  return (
    <section
      className="reading-calendar cover-calendar"
      aria-label="독서 캘린더"
    >
      <h2 className="cover-calendar-title">독서 캘린더</h2>
      <div className="cover-calendar-filters" aria-label="달력 기록 필터">
        {[false, true].map((value) => (
          <button
            key={String(value)}
            type="button"
            aria-pressed={completedOnly === value}
            onClick={() => setCompletedOnly(value)}
          >
            {completedOnly === value && <span aria-hidden="true">✓ </span>}
            {value ? "완독 보기" : "전체 보기"}
          </button>
        ))}
      </div>
      <div className="cover-calendar-month">
        <button
          type="button"
          aria-label="이전 달"
          onClick={() => setMonth(new Date(year, index - 1, 1))}
        >
          ‹
        </button>
        <h3 aria-live="polite">
          {year}.{String(index + 1).padStart(2, "0")}
        </h3>
        <button
          type="button"
          aria-label="다음 달"
          onClick={() => setMonth(new Date(year, index + 1, 1))}
        >
          ›
        </button>
      </div>
      <div className="cover-calendar-grid">
        {["일", "월", "화", "수", "목", "금", "토"].map((day) => (
          <span className="cover-calendar-weekday" key={day}>
            {day}
          </span>
        ))}
        {Array.from({ length: offset }, (_, i) => (
          <span
            className="cover-calendar-blank"
            aria-hidden="true"
            key={`blank-${i}`}
          />
        ))}
        {Array.from({ length: days }, (_, i) => {
          const date = dateKey(year, index, i + 1);
          const entries = entriesOn(date);
          const first = entries.find((record) => record.startDate === date || record.endDate === date);
          const memos = entries.filter((record) => hasMemo(record, date));
          const completed = first?.endDate === date;
          const started = first?.startDate === date;
          return (
            <button
              className="cover-calendar-day"
              key={date}
              type="button"
              aria-label={`${date}, 기록 ${entries.length}권, 메모 ${memos.length}개${completed ? ", 완독" : ""}`}
              aria-current={date === todayKey ? "date" : undefined}
              aria-haspopup="dialog"
              onClick={() => openDate(date)}
            >
              <span className="cover-calendar-tile">
                {first && <Cover book={first.book} />}
                {!first && memos.length > 0 && <span className="calendar-memo-preview">{memos[0].logs[date]}</span>}
                {memos.length > 0 && <span className="calendar-memo-badge">메모 {memos.length}</span>}
                {first && <span className="cover-calendar-done">{started && completed ? "시작 · 완독" : completed ? "완독" : "시작"}</span>}
                {entries.length > 1 && (
                  <span className="cover-calendar-more">
                    +{entries.length - 1}권
                  </span>
                )}
              </span>
              <span className="cover-calendar-number">{i + 1}</span>
            </button>
          );
        })}
      </div>
      <p className="cover-calendar-hint">
        {completedOnly
          ? "완독일이 기록된 책을 보여줘요."
          : "독서 시작일·완독일에 표지가, 메모를 남긴 날짜에 메모가 나타나요."}{" "}
        날짜를 눌러 기록을 남겨보세요.
      </p>
      <Modal
        open={!!selected}
        close={() => { setSelected(null); setDeleteTarget(null); }}
        title={`${selected || ""} 독서 기록`}
      >
        <div className="cover-calendar-detail">
          {entriesOn(selected, false).map((record) => (
            <button
              key={record.id}
              type="button"
              className="cover-calendar-entry"
              aria-pressed={book?.id === record.id}
              onClick={() => {
                setBookId(record.id);
                setSaved("");
              }}
            >
              <Cover book={record.book} />
              <span>
                <strong>{record.book.title}</strong>
                <small>
                  {record.startDate === selected && "독서 시작 · "}
                  {record.endDate === selected && "완독 · "}
                  {record.logs?.[selected] || "날짜 기록"}
                </small>
              </span>
            </button>
          ))}
          {book && selected ? (
            <form
              key={selected + book.id + (book.logs?.[selected] || "")}
              className="editor-form"
              onSubmit={save}
            >
              <label>
                기록할 책
                <select
                  value={book.id}
                  onChange={(event) => {
                    setBookId(event.target.value);
                    setSaved("");
                  }}
                >
                  {records.map((record) => (
                    <option value={record.id} key={record.id}>
                      {record.book.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                독서 메모
                <textarea
                  aria-label="독서 메모"
                  name="memo"
                  rows={4}
                  maxLength={3000}
                  defaultValue={book.logs?.[selected] || ""}
                  placeholder="읽은 페이지나 기억하고 싶은 문장을 적어주세요."
                />
              </label>
              <button className="primary-btn" disabled={busy}>
                {busy ? "저장 중…" : "기록 저장"}
              </button>
              {hasMemo(book, selected) && <button type="button" className="danger-btn" disabled={busy}
                onClick={() => setDeleteTarget({ id: book.id, date: selected })}>메모 삭제</button>}
              <small>메모 삭제는 확인창에서 ‘예’를 눌러야 완료돼요.</small>
              <p role="status">{saved || notice}</p>
            </form>
          ) : (
            <p>서재에 책을 담으면 날짜별 독서 기록을 남길 수 있어요.</p>
          )}
        </div>
      </Modal>
      <Modal open={!!deleteTarget} close={() => setDeleteTarget(null)} title="메모 삭제 확인">
        <p>삭제하시겠습니까?</p>
        <p className="home-hint">선택한 날짜의 메모만 삭제돼요.</p>
        <div className="memo-delete-actions">
          <button type="button" className="outline-btn" disabled={busy} onClick={() => setDeleteTarget(null)}>아니오</button>
          <button type="button" className="danger-btn" disabled={busy} onClick={deleteMemo}>{busy ? "삭제 중…" : "예"}</button>
        </div>
        <p role="status">{busy ? "삭제 중…" : notice}</p>
      </Modal>
    </section>
  );
}
