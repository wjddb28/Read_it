import { useState } from "react";
import { useLibrary } from "./LibraryContext";
import { Cover } from "./BookCard";
import Modal from "./Modal";
import "../../../static/css/react/calendar.css";

function dateKey(year, month, day) {
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export default function ReadingCalendar() {
  const { records, update, busy, notice } = useLibrary();
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
  const year = month.getFullYear();
  const index = month.getMonth();
  const offset = new Date(year, index, 1).getDay();
  const days = new Date(year, index + 1, 0).getDate();
  const book = records.find((record) => record.id === bookId) || records[0];

  function entriesOn(date, filter = completedOnly) {
    return records.filter((record) =>
      filter
        ? record.status === "COMPLETED" && record.endDate === date
        : record.startDate === date || record.endDate === date,
    );
  }

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
    const logs = { ...book.logs };
    if (memo) logs[selected] = memo;
    else delete logs[selected];
    if (await update(book.id, { logs }))
      setSaved("이 날짜의 독서 메모를 저장했어요.");
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
          const first = entries[0];
          const completed = first?.endDate === date;
          const started = first?.startDate === date;
          return (
            <button
              className="cover-calendar-day"
              key={date}
              type="button"
              aria-label={`${date}, 기록 ${entries.length}권${completed ? ", 완독" : ""}`}
              aria-current={date === todayKey ? "date" : undefined}
              aria-haspopup="dialog"
              onClick={() => openDate(date)}
            >
              <span className="cover-calendar-tile">
                {first && <Cover book={first.book} />}
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
          : "독서 시작일과 완독일에만 표지가 나타나요."}{" "}
        날짜를 눌러 기록을 남겨보세요.
      </p>
      <Modal
        open={!!selected}
        close={() => setSelected(null)}
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
              key={selected + book.id}
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
                오늘의 독서 메모
                <textarea
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
              <small>메모를 비우고 저장하면 해당 날짜의 메모가 삭제돼요.</small>
              <p role="status">{saved || notice}</p>
            </form>
          ) : (
            <p>서재에 책을 담으면 날짜별 독서 기록을 남길 수 있어요.</p>
          )}
        </div>
      </Modal>
    </section>
  );
}
