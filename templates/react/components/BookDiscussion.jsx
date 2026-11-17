import { useEffect, useState } from 'react';
import { useCommunity } from './CommunityContext';
import { useAuth } from './AuthContext';
import { useLibrary } from './LibraryContext';
import { community } from '../communityApi';
import PostComposer from './PostComposer';
import CommunityPostRow from './CommunityPostRow';
import ReaderProfile from './ReaderProfile';
export default function BookDiscussion({ book }) {
  const { records } = useLibrary();
  const completed = records.some((record) => record.id === String(book.isbn) && record.status === 'COMPLETED');
  const { user } = useAuth(); const { revision, progress, setReadingProgress } = useCommunity();
  const [data, setData] = useState(null), [error, setError] = useState('');
  const [compose, setCompose] = useState(false), [reader, setReader] = useState(null);
  useEffect(() => {
    if (!book.isbn) return; const controller = new AbortController(); setError(''); setData(null);
    community('/posts?' + new URLSearchParams({ isbn: book.isbn, kind: 'quote' }), { signal: controller.signal })
      .then(setData).catch((e) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [book.isbn, revision, user?.id]);
  if (!book.isbn) return null;
  return <section className="book-community-section"><h3>이 책의 서평</h3>
    {book.isbn != null && <label className="book-progress-label">내 독서 진도<select aria-label="이 책의 내 독서 진도" disabled={completed} value={completed ? 2 : progress[book.isbn]} onChange={async (event) => {
      try { await setReadingProgress(book.isbn, event.target.value); } catch (e) { setError(e.message); }
    }}><option value={0}>초반</option><option value={1}>중반</option><option value={2}>결말</option></select></label>}
    {error && <p role="alert">{error}</p>}{data && (data.posts.length ? data.posts.map((post) => <CommunityPostRow key={post.id} post={post} onAuthor={setReader} />) : <p>등록된 글이 없어요.</p>)}
    <div className="book-community-links"><button className="outline-btn" onClick={() => setCompose(true)}>서평 쓰기</button></div>
    <PostComposer open={compose} close={() => setCompose(false)} initialBook={book} initialKind="quote" />
    <ReaderProfile profileId={reader} close={() => setReader(null)} />
  </section>;
}
