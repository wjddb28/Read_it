import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../components/AuthContext";
import { useLibrary } from "../components/LibraryContext";
import { dateKey, hasMemo, useLocalDate, weekDays } from "../readingDates";
export default function HomePage() {
  const { user, loading } = useAuth();
  const { records, updateLog, notice, busy } = useLibrary();
  const [today, refreshDate] = useLocalDate();
  const todayKey = dateKey(today);
  const days = weekDays(today);
  const firstKey = dateKey(days[0]);
  const [bookId, setBookId] = useState("");
  const [message, setMessage] = useState("");
  const book = records.find((record) => record.id === bookId) || records.find((record) => record.status === "READING") || records[0];
  const inWeek = (day) => day >= firstKey && day <= todayKey;
  const memoCount = records.reduce((sum, record) => sum + Object.keys(record.logs || {}).filter((day) => inWeek(day) && hasMemo(record, day)).length, 0);
  const started = records.filter((record) => inWeek(record.startDate)).length;
  const completed = records.filter((record) => inWeek(record.endDate)).length;
  const dailyRecords = records.filter((record) => hasMemo(record, todayKey));
  async function save(event) {
    event.preventDefault(); setMessage("");
    // Recheck the real local date even when the tab stayed open overnight.
    if (dateKey(new Date()) !== todayKey) {
      refreshDate(); setMessage("날짜가 바뀌었어요. 오늘 날짜를 확인하고 다시 기록해주세요."); return;
    }
    if (!book) return;
    const memo = String(new FormData(event.currentTarget).get("memo") || "").trim();
    if (!memo) { setMessage("오늘의 독서 메모를 입력해주세요. 메모 삭제는 내 서재에서 할 수 있어요."); return; }
    if (await updateLog(book.id, todayKey, memo)) setMessage("오늘의 독서 기록을 저장했어요.");
  }
  if (loading) return <main className="container workspace-page"><p role="status">로그인 확인 중…</p></main>;
  return <main className="container workspace-page reading-home">
    <div className="page-top"><div><p className="section-kicker">TODAY, ONE PAGE</p>
      <h1>{user ? `${user.nickname}의 오늘 독서` : "오늘도, 한 페이지"}</h1>
      <p className="page-subtitle">이번 주를 돌아보고, 오늘 읽은 한 줄을 남겨요.</p></div>
      <div className="home-links"><Link className="outline-btn" to="/search">책 찾기</Link>
        <Link className="primary-btn" to="/library">내 서재</Link></div></div>
    {user ? <>
      <section className="weekly-record" aria-label="이번 주 활동 기록">
        <div className="section-title-row"><h2>이번 주 활동</h2>
          <span>{days[0].getMonth() + 1}.{days[0].getDate()} – {days[6].getMonth() + 1}.{days[6].getDate()}</span></div>
        <div className="week-summary">{[["독서 메모", memoCount], ["읽기 시작", started], ["완독", completed]].map(([label, count]) =>
          <div key={label}><span>{label}</span><strong>{count}<small>{label === "독서 메모" ? "개" : "권"}</small></strong></div>)}</div>
        <div className="week-days">{days.map((day) => {
          const key = dateKey(day), future = key > todayKey;
          const count = future ? 0 : records.reduce((sum, record) => sum + Number(hasMemo(record, key)) + Number(record.startDate === key) + Number(record.endDate === key), 0);
          const content = <><span>{["일", "월", "화", "수", "목", "금", "토"][day.getDay()]}</span><strong>{day.getDate()}</strong><small>{future ? "예정" : count ? `활동 ${count}` : "기록 없음"}</small></>;
          return future ? <div className="week-day is-future" key={key}>{content}</div>
            : <Link key={key} className={"week-day" + (key === todayKey ? " is-today" : "")}
              to={key === todayKey ? "#today-record" : `/library?date=${key}`}
              aria-label={`${key} ${key === todayKey ? "오늘 기록 작성" : "내 서재에서 기록 보기"}`}>{content}</Link>;
        })}</div>
        <p className="home-hint">다른 날짜의 기록은 <Link to="/library">내 서재</Link>에서 작성하고 수정할 수 있어요.</p>
      </section>
      <section className="today-record" id="today-record" aria-label="오늘 독서 기록">
        <div className="section-title-row"><h2>오늘의 독서 기록</h2><time dateTime={todayKey}>{todayKey}</time></div>
        {book ? <form key={`${todayKey}:${book.id}:${book.logs?.[todayKey] || ""}`} className="editor-form" onSubmit={save}>
          <label>기록할 책<select aria-label="오늘 기록할 책" value={book.id} onChange={(event) => { setBookId(event.target.value); setMessage(""); }}>
            {records.map((record) => <option key={record.id} value={record.id}>{record.book.title}</option>)}
          </select></label>
          <label>오늘의 독서 메모<textarea aria-label="오늘의 독서 메모" name="memo" rows={4} maxLength={3000} defaultValue={book.logs?.[todayKey] || ""}
            placeholder="오늘 읽은 페이지나 기억에 남은 문장을 적어주세요." /></label>
          <button className="primary-btn" disabled={busy}>{busy ? "저장 중…" : "오늘 기록 저장"}</button>
          <p role="status">{message || notice}</p>
        </form> : <p>서재에 책을 담으면 오늘의 독서 기록을 남길 수 있어요. <Link to="/search">책 찾기</Link></p>}
        {dailyRecords.length > 0 && <div className="today-memos"><h3>오늘 남긴 메모</h3>{dailyRecords.map((record) =>
          <article key={record.id}><strong>{record.book.title}</strong><p>{record.logs[todayKey]}</p></article>)}</div>}
      </section>
    </> : <section className="today-record"><h2>나의 독서 습관을 만들어봐요</h2><p>로그인하면 이번 주 활동과 오늘의 독서 기록을 모아볼 수 있어요.</p>
      <Link className="primary-btn" to="/login">로그인하기</Link></section>}
  </main>;
}
