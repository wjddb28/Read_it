import { useState } from 'react';
import { Link } from 'react-router-dom';
import Modal from './Modal';
import { dateKey, hasDailyLog, hasMemo, hasReadingTime } from '../readingDates';
import { activityCounts, heatmapDays, streakStats } from '../streaks';

export default function ReadingStreak({ records, today }) {
  const [weeks, setWeeks] = useState(53);
  const [hovered, setHovered] = useState('');
  const [selected, setSelected] = useState(null);
  const activities = selected ? records.filter(record => record.startDate === selected || record.endDate === selected || hasDailyLog(record, selected)) : [];
  const counts = activityCounts(records, [], today);
  const stats = streakStats(counts, today), last = dateKey(today);
  const days = heatmapDays(today, weeks);
  const months = Array.from({ length: weeks }, (_, column) => {
    const week = days.slice(column * 7, column * 7 + 7);
    const first = week.find(day => day.getDate() === 1 && dateKey(day) <= last);
    const day = first || (column === 0 ? week[0] : null);
    return day ? { column, year: day.getFullYear(), month: day.getMonth() + 1 } : null;
  }).filter(Boolean);

  return <section className="reading-streak heatmap-streak" aria-label="독서 스트릭 캘린더 미리보기">
    <div className="section-title-row"><div><span>나의 독서 스트릭</span><h3>현재 <strong>{stats.current}일</strong> 연속 독서</h3></div>
      <div className="streak-controls"><Link className="text-btn" to="/library">전체 캘린더 →</Link>
        <label><span className="sr-only">스트릭 표시 기간</span><select aria-label="스트릭 표시 기간" value={weeks} onChange={event => { setWeeks(Number(event.target.value)); setHovered(''); }}>
          <option value={13}>최근 3개월</option><option value={26}>최근 6개월</option><option value={53}>최근 1년</option>
        </select></label></div>
    </div>
    <div className="streak-heatmap-scroll" tabIndex={0} aria-label="독서 스트릭, 가로로 스크롤할 수 있어요">
      <div className="streak-heatmap-layout" style={{ '--streak-weeks': weeks }}>
        <div className="streak-weekdays" aria-hidden="true">{['일','월','화','수','목','금','토'].map(day => <span key={day}>{day}</span>)}</div>
        <div className="streak-heatmap-grid" onMouseLeave={() => setHovered('')}>
          {days.map(day => {
            const key = dateKey(day), count = counts[key] || 0, future = key > last;
            const starts = !future ? records.filter(record => record.startDate === key) : [];
            const ends = !future ? records.filter(record => record.endDate === key) : [];
            const label = `${key} · ${future ? '예정' : `독서 기록 ${count}개`}${starts.length ? ` · 읽기 시작 ${starts.length}권` : ''}${ends.length ? ` · 완독 ${ends.length}권` : ''}`;
            const className = `streak-dot level-${Math.min(count, 4)}${starts.length ? ' has-start' : ''}${ends.length ? ' has-completion' : ''}${future ? ' is-future' : ''}`;
            const marker = ends.length ? '★' : starts.length ? '☆' : '';
            return future ? <span key={key} className={className} title={label} aria-label={label} />
              : <button type="button" key={key} onClick={() => setSelected(key)} className={className} title={label} aria-label={label} aria-current={key === last ? 'date' : undefined}
                  onMouseEnter={() => setHovered(label)} onFocus={() => setHovered(label)} onBlur={() => setHovered('')}><span aria-hidden="true">{marker}</span></button>;
          })}
        </div>
        <div className="streak-month-labels" aria-label="스트릭 연도와 월">{months.map(({ column, year, month }, index) =>
          <span key={`${year}-${month}`} style={{ gridColumn: column + 1 }}><span className="streak-year-label">{index === 0 || month === 1 ? `${year}년` : '\u00a0'}</span><span>{month}월</span></span>
        )}</div>
      </div>
    </div>
    <p className="streak-hover-detail" role="status">{hovered || '칸에 마우스를 올리면 날짜와 독서 기록이 표시돼요.'}</p>
    <div className="streak-footer"><small>최장 {stats.longest}일 · 기록한 날 {stats.activeDays}일</small>
      <div className="streak-symbols"><small><b className="start-symbol">☆</b> 읽기 시작</small><small><b className="end-symbol">★</b> 완독</small>
        <div className="streak-legend" aria-label="독서 기록 수에 따른 색상"><small>적음</small>{[0,1,2,3,4].map(level => <span key={level} className={'streak-dot level-' + level} aria-hidden="true" />)}<small>많음</small></div>
      </div>
    </div>
    <p className="home-hint">독서 시작·완독·메모·읽은 시간만 반영해요. 칸을 누르면 이 화면에서 해당 날짜의 활동을 간단히 확인할 수 있어요.</p>
    <Modal open={!!selected} close={() => setSelected(null)} title={`${selected || ''} 독서 활동`}>
      <div className="streak-activity-preview">
        {activities.length ? activities.map(record => <article key={record.id}><h3>{record.book.title}</h3>
          <div className="streak-activity-tags">{record.startDate === selected && <span>☆ 읽기 시작</span>}{record.endDate === selected && <span>★ 완독</span>}{hasReadingTime(record, selected) && <span>{record.readingMinutes[selected]}분 읽음</span>}</div>
          {hasMemo(record, selected) && <p className="streak-memo-excerpt">{record.logs[selected].length > 160 ? record.logs[selected].slice(0, 160) + '…' : record.logs[selected]}</p>}
        </article>) : <p>이 날짜에는 독서 활동이 없어요.</p>}
      </div>
    </Modal>
  </section>;
}
