import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { community } from '../communityApi';
import { useCommunity } from './CommunityContext';

export default function RandomOneLineReviews() {
  const { revision } = useCommunity();
  const location = useLocation();
  const [lines, setLines] = useState(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setLines(null); setError('');
    community('/random-lines', { signal: controller.signal, cache: 'no-store' })
      .then(data => setLines(data.lines))
      .catch(error => { if (error.name !== 'AbortError') setError('한줄평을 불러오지 못했어요.'); });
    return () => controller.abort();
  }, [revision, retry]);
  return <section className="community-writing-note random-line-reviews" aria-label="랜덤 한줄평">
    <h3>짧아도 좋은 이야기</h3>
    {error ? <div role="status"><p>{error}</p><button type="button" className="text-btn" onClick={() => setRetry(retry + 1)}>다시 불러오기</button></div>
      : !lines ? <p role="status">한줄평을 고르는 중…</p>
      : lines.length ? <div className="random-lines-list">{lines.map(line => <Link key={line.id} className="random-line-card"
          to={'/community/posts/' + encodeURIComponent(line.id)} state={{ returnTo: location.pathname + location.search }}>
          {line.book && <strong className="random-line-book">『{line.book.title}』</strong>}
          <blockquote>{line.body}</blockquote>
          <span className="random-line-meta"><span>{line.author.nickname}</span>{line.recommended !== null && <small>{line.recommended ? '추천해요' : '추천하지 않아요'}</small>}</span>
        </Link>)}</div>
      : <p>아직 공개된 한줄평이 없어요. 첫 한줄평을 남겨보세요.</p>}
  </section>;
}
