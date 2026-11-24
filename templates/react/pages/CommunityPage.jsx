import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../components/AuthContext';
import { useCommunity } from '../components/CommunityContext';
import Pagination from '../components/Pagination';
import PostComposer from '../components/PostComposer';
import CommunityPostRow from '../components/CommunityPostRow';
import ReaderProfile from '../components/ReaderProfile';
import RandomOneLineReviews from '../components/RandomOneLineReviews';
import { categoryLabels, community } from '../communityApi';
export default function CommunityPage() {
  const { user } = useAuth(); const { revision } = useCommunity(); const [params, setParams] = useSearchParams();
  const kind = ['quote', 'free', 'rating'].includes(params.get('kind')) ? params.get('kind') : 'all', category = params.get('category') || 'all', mode = params.get('mode') === 'neighbors' ? 'neighbors' : 'all', sort = params.get('sort') || 'recent';
  const isbn = params.get('isbn') || '', author = params.get('author') || '', page = Math.max(1, Number(params.get('page')) || 1);
  const q = params.get('q') || '';
  const [query, setQuery] = useState(q), [data, setData] = useState(null), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  const navigate = useNavigate();
  const [compose, setCompose] = useState(false), [reader, setReader] = useState(null);
  function change(patch) { const next = new URLSearchParams(params); Object.entries({ page: '1', ...patch }).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key)); setParams(next); }
  useEffect(() => { setQuery(q); }, [q]);
  useEffect(() => { setReader(null); }, [author, isbn]);
  useEffect(() => {
    if (params.get('post')) { const list = new URLSearchParams(params); list.delete('post'); navigate('/community/posts/' + encodeURIComponent(params.get('post')), { replace: true, state: { returnTo: '/community' + (list.size ? '?' + list : '') } }); }
    if (params.get('write') === '1') { setCompose(true); const list = new URLSearchParams(params); list.delete('write'); setParams(list, { replace: true }); }
  }, [params.get('post'), params.get('write')]);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError('');
    const values = { kind, category: kind === 'quote' || kind === 'rating' ? 'all' : category, mode, sort, page: String(page), ...(isbn ? { isbn } : {}), ...(author ? { author } : {}), ...(q ? { q } : {}) };
    community('/posts?' + new URLSearchParams(values), { signal: controller.signal }).then(setData).catch((e) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [kind, category, mode, sort, page, isbn, author, q, revision, retry, user?.id]);
  const [activity, setActivity] = useState(null), [activityError, setActivityError] = useState('');
  useEffect(() => {
    const controller = new AbortController(); setActivity(null); setActivityError('');
    if (user?.communityReady) community('/me/activity', { signal: controller.signal }).then(setActivity).catch(e => { if (e.name !== 'AbortError') setActivityError('활동 기록을 불러오지 못했어요.'); });
    return () => controller.abort();
  }, [user?.id, user?.communityReady, revision, retry]);
  const tabs = { all: '전체', quote: '서평', free: '자유게시판', rating: '다른 독자 평점' };
  return <main className="container workspace-page community-page-v2">
    <header className="community-page-heading"><div><h1>커뮤니티</h1></div>
      <button className="primary-btn" onClick={() => setCompose(true)}>글 쓰기 ＋</button></header>
    <div className="community-layout-v2"><section className="community-feed-v2" aria-label="커뮤니티 글 목록">
      <nav className="community-kind-tabs" aria-label="게시판 종류">{Object.entries(tabs).map(([value, label]) => <button key={value} aria-pressed={kind === value} onClick={() => change({ kind: value, category: value === 'quote' || value === 'rating' ? '' : category })}>{label}</button>)}</nav>
      <div className="community-simple-filters">
        <label>글 모아보기<select aria-label="피드 선택" value={mode} onChange={event => change({ mode: event.target.value })}><option value="all">전체 글</option><option value="neighbors">취향이 비슷한 독자</option></select></label>
        {(kind === 'all' || kind === 'free') && <label>주제<select aria-label="글 주제" value={category} onChange={event => change({ category: event.target.value })}><option value="all">전체 주제</option>{Object.entries(categoryLabels).map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
        <label>정렬<select aria-label="커뮤니티 정렬" value={sort} onChange={event => change({ sort: event.target.value })}><option value="recent">최신순</option><option value="recommended">추천순</option></select></label>
      </div>
      <form className="community-search-v2" onSubmit={(event) => { event.preventDefault(); change({ q: query.trim() }); }}><input aria-label="커뮤니티 책 제목 검색" value={query} onChange={(event) => setQuery(event.target.value)} maxLength={200} placeholder="책 제목" /><button className="outline-btn">검색</button></form>
      {(isbn || author) && <p className="community-scope"><button className="text-btn" onClick={() => change({ isbn: '', author: '', post: '' })}>전체로 돌아가기</button></p>}
      {mode !== 'all' && !user && <p className="community-scope"><Link to="/login">로그인</Link>이 필요해요.</p>}
      {error ? <div className="community-empty"><p role="alert">{error}</p><button className="outline-btn" onClick={() => setRetry(retry + 1)}>다시 시도</button></div>
        : !data ? <p className="community-empty" role="status">이야기를 불러오는 중…</p>
        : data.posts.length ? <><div className="community-feed-count">이야기 {data.total}개</div>{data.posts.map((post) => <CommunityPostRow key={post.id} post={post} onAuthor={setReader} />)}
          <Pagination page={data.page} pages={data.total_pages} onChange={(value) => change({ page: String(value) })} /></>
        : <div className="community-empty"><h2>{mode === 'neighbors' ? '아직 취향이 비슷한 독자의 글이 없어요' : '게시글이 없어요'}</h2>
          <button className="outline-btn" onClick={() => setCompose(true)}>글 쓰기</button></div>}
    </section>
    <aside className="community-aside-v2"><section><h2>{user ? `${user.nickname}의 책 이야기` : '함께 읽는 즐거움'}</h2>
      {user?.bio && <p>{user.bio}</p>}{user && <div className="community-my-counts" aria-label="내 커뮤니티 활동 기록">
        {activity ? [['게시물', activity.posts.filter(post => post.kind !== 'line').length], ['댓글', activity.counts.comments], ['한줄평', activity.counts.lines]].map(([label,count]) => <div key={label}><strong>{count}</strong><span>{label}</span></div>) : <p role="status">{activityError || (user.communityReady ? '활동 기록 불러오는 중…' : '커뮤니티 연결을 확인해주세요.')}</p>}
      </div>}{activityError && <button className="text-btn" onClick={() => setRetry(retry + 1)}>다시 불러오기</button>}
      <Link to={user ? '/profile' : '/login'} className="outline-btn">{user ? '내 활동 보기' : '로그인하기'}</Link></section>
      <RandomOneLineReviews />
      <Link className="text-btn" to="/search">이야기할 책 찾기 →</Link></aside></div>
    <PostComposer open={compose} close={() => setCompose(false)} initialKind={kind === 'free' ? 'free' : 'quote'} />
    <ReaderProfile profileId={reader} close={() => setReader(null)} />
  </main>;
}
