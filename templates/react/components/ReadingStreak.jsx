import { useEffect, useState } from 'react';
import { useAuth } from './AuthContext';
import { useCommunity } from './CommunityContext';
import { community } from '../communityApi';
import { dateKey } from '../readingDates';
import { activityCounts, heatmapDays, streakStats } from '../streaks';
export default function ReadingStreak({ records, today }) {
  const { user } = useAuth(); const { revision } = useCommunity();
  const [days, setDays] = useState([]), [weeks, setWeeks] = useState(13), [error, setError] = useState('');
  useEffect(() => {
    if (!user?.communityReady) { setDays([]); return; }
    let active = true; setError('');
    community('/me/activity').then((data) => { if (active) setDays(data.activityDays); }).catch(() => { if (active) setError('커뮤니티 활동은 잠시 불러오지 못했어요. 독서 기록으로 표시하고 있어요.'); });
    return () => { active = false; };
  }, [user?.id, user?.communityReady, revision]);
  const counts = activityCounts(records, days, today), stats = streakStats(counts, today), last = dateKey(today);
  return <section className="reading-streak" aria-label="독서 활동 스트릭"><div className="section-title-row"><div><span>나의 스트릭</span><h3>현재 <strong>{stats.current}일</strong> 연속 활동</h3></div>
    <label>표시 기간<select aria-label="스트릭 표시 기간" value={weeks} onChange={(event) => setWeeks(Number(event.target.value))}><option value={13}>최근 3개월</option><option value={26}>최근 6개월</option><option value={52}>최근 1년</option></select></label></div>
    <div className="streak-scroll"><div className="streak-grid" style={{ gridTemplateColumns: `repeat(${weeks}, 12px)` }}>
      {heatmapDays(today, weeks).map((day) => { const key = dateKey(day), count = counts[key] || 0, future = key > last;
        return <span key={key} className={'streak-cell level-' + Math.min(count, 4) + (future ? ' is-future' : '')} role="img" aria-label={`${key} ${future ? '예정' : `활동 ${count}개`}`} title={`${key} · 활동 ${count}개`} />;
      })}</div></div>
    <div className="streak-footer"><small>최장 {stats.longest}일 · 활동한 날 {stats.activeDays}일</small><div className="streak-legend"><small>적음</small>{[0,1,2,3,4].map((n) => <span key={n} className={'streak-cell level-' + n} />)}<small>많음</small></div></div>
    <p className="home-hint">독서 메모·시작일·완독일과 커뮤니티 글·댓글을 기록해요. 오늘 기록이 없으면 어제까지의 연속 활동을 표시해요.</p>{error && <p role="status">{error}</p>}
  </section>;
}
