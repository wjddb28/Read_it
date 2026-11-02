import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useCommunity } from './CommunityContext';
import { useAuth } from './AuthContext';
import { useLibrary } from './LibraryContext';
import { community } from '../communityApi';
import PostComposer from './PostComposer';
import PostDetail from './PostDetail';
import CommunityPostRow from './CommunityPostRow';
import ReaderProfile from './ReaderProfile';
export default function BookDiscussion({ book }) {
  const { records } = useLibrary();
  const completed = records.some((record) => record.id === String(book.isbn) && record.status === 'COMPLETED');
  const { user } = useAuth(); const { revision, progress, setReadingProgress } = useCommunity();
  const [kind, setKind] = useState('quote'), [data, setData] = useState(null), [summary, setSummary] = useState(null), [error, setError] = useState('');
  const [compose, setCompose] = useState(false), [selected, setSelected] = useState(null), [reader, setReader] = useState(null);
  useEffect(() => {
    if (!book.isbn) return; const controller = new AbortController(); setError(''); setData(null);
    Promise.all([community('/posts?' + new URLSearchParams({ isbn: book.isbn, kind } ), { signal: controller.signal }), community('/books/' + book.isbn + '/summary', { signal: controller.signal })])
      .then(([feed, counts]) => { setData(feed); setSummary(counts); }).catch((e) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [book.isbn, kind, revision, user?.id]);
  if (!book.isbn) return null;
  return <section className="book-community-section"><h3>이 책을 읽은 사람들</h3>
    {summary && <p className="book-community-summary">{summary.ratingCount ? `평점 ★ ${summary.averageRating} · ${summary.ratingCount}개의 평점` : '아직 공개된 평점이 없어요.'}
      {' · '}한줄평 {summary.lineCount}개{summary.lineCount > 0 ? ` 중 ${summary.recommended}명이 추천해요` : ''}</p>}
    {progress[book.isbn] != null && <label className="book-progress-label">내 독서 진도<select aria-label="이 책의 내 독서 진도" disabled={completed} value={completed ? 2 : progress[book.isbn]} onChange={async (event) => {
      try { await setReadingProgress(book.isbn, event.target.value); } catch (e) { setError(e.message); }
    }}><option value={0}>초반</option><option value={1}>중반</option><option value={2}>결말</option></select></label>}
    <div className="book-community-tabs">{[['quote','책 연결 글'],['line','한줄평'],['rating','다른 독자 평점']].map(([value,label]) => <button key={value} aria-pressed={kind === value} onClick={() => setKind(value)}>{label}</button>)}</div>
    {error && <p role="alert">{error}</p>}{data && (data.posts.length ? data.posts.slice(0,3).map((post) => <CommunityPostRow key={post.id} post={post} onOpen={setSelected} onAuthor={setReader} />) : <p>아직 이야기가 없어요. 첫 감상을 남겨주세요.</p>)}
    <div className="book-community-links"><button className="outline-btn" onClick={() => setCompose(true)}>{kind === 'line' ? '한줄평 남기기' : '책 이야기 쓰기'}</button>
      <Link className="text-btn" to={'/community?' + new URLSearchParams({ isbn: book.isbn, kind })}>전체 {kind === 'line' ? '한줄평' : kind === 'rating' ? '평점' : '책 이야기'} 보러가기 →</Link></div>
    <PostComposer open={compose} close={() => setCompose(false)} initialBook={book} initialKind={kind === 'line' ? 'line' : 'quote'} />
    {selected && <PostDetail key={selected} postId={selected} close={() => setSelected(null)} />}
    <ReaderProfile profileId={reader} close={() => setReader(null)} />
  </section>;
}
