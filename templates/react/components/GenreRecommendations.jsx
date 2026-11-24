import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { useLibrary } from './LibraryContext';
import { community } from '../communityApi';
import BookCard from './BookCard';

export default function GenreRecommendations() {
  const { user } = useAuth();
  const { records, loading } = useLibrary();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const signature = JSON.stringify([
    user?.likedGenres, user?.dislikedGenres,
    records.map(record => [record.id, record.rating, record.content]),
  ]);

  useEffect(() => {
    if (!user?.onboarded || loading) return;
    const controller = new AbortController();
    setData(null);
    setError('');
    community('/recommendations', { signal: controller.signal })
      .then(setData)
      .catch(error => { if (error.name !== 'AbortError') setError(error.message); });
    return () => controller.abort();
  }, [user?.id, user?.onboarded, signature, retry, loading]);

  if (!user?.onboarded) return null;

  return <section className="genre-recommendations">
    <div className="section-title-row">
      <h2>내 취향으로 고른 책</h2>
      <Link className="text-btn" to="/profile">취향 수정 →</Link>
    </div>
    {error ? <p role="alert">{error} <button className="text-btn" onClick={() => setRetry(n => n + 1)}>다시 시도</button></p>
      : !data ? <p role="status">취향 도서를 고르고 있어요…</p>
      : data.books.length ? <div className="genre-book-grid">{data.books.map(book =>
        <div className="genre-recommendation-item" key={book.isbn}>
          <div className="genre-match-summary">
            {!!book.matchedPreferredGenres?.length && <p>선호 장르: {book.matchedPreferredGenres.join(', ')}</p>}
            {book.similarShelfTitle && <p>내 서재: 「{book.similarShelfTitle}」</p>}
          </div>
          <BookCard book={book} showDescription={false} />
        </div>
      )}</div> : <p>{data.message}</p>}
  </section>;
}
