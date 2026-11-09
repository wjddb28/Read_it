import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { community } from '../communityApi';
import BookCard from './BookCard';
export default function GenreRecommendations() {
  const { user } = useAuth(); const [data,setData]=useState(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const signature=JSON.stringify([user?.likedGenres,user?.dislikedGenres]);
  useEffect(()=>{if(!user?.onboarded)return;const controller=new AbortController();setData(null);setError('');community('/recommendations',{signal:controller.signal}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>controller.abort();},[user?.id,user?.onboarded,signature,retry]);
  if(!user?.onboarded)return null;
  return <section className="genre-recommendations"><div className="section-title-row"><h2>내 취향으로 고른 책</h2><Link className="text-btn" to="/profile">취향 수정 →</Link></div>
    {error?<p role="status">{error} <button className="text-btn" onClick={()=>setRetry(retry+1)}>다시 시도</button></p>:!data?<p role="status">취향 도서를 고르고 있어요…</p>:data.books.length?<div className="genre-book-grid">{data.books.map(book=><div className="genre-recommendation-item" key={book.isbn}><p className="genre-match-summary">선호 장르 {book.matchedGenreCount ?? book.matchedGenres?.length ?? 0}개 일치{book.matchedGenres?.length ? ` · ${book.matchedGenres.join(' · ')}` : ''}</p><BookCard book={book} showDescription={false}/></div>)}</div>:<p>{data.message}</p>}
  </section>;
}
