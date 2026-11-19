import { Link, useLocation } from 'react-router-dom';
import { categoryLabels } from '../communityApi';
export default function CommunityPostRow({ post, onAuthor }) {
  const location = useLocation();
  const spoiler = post.hasSpoiler || post.spoilerHidden;
  const tasteReason = post.tasteMatch?.reason || [
    post.tasteMatch?.sharedBooks ? `같이 읽은 책 ${post.tasteMatch.sharedBooks}권` : '',
    ...(Array.isArray(post.tasteMatch?.sharedGenres) ? post.tasteMatch.sharedGenres : []),
  ].filter(Boolean).join(' · ');
  return <article className="community-post-row">
    <div className="post-meta"><span className={'post-category category-' + post.category}>{post.kind === 'quote' ? '서평' : categoryLabels[post.category]}</span>
      {post.kind === 'line' && !post.spoilerHidden && <span className={'line-tag ' + (post.recommended ? 'is-yes' : 'is-no')}>{post.recommended ? '추천해요' : '추천하지 않아요'}</span>}
      <time>{new Date(post.createdAt).toLocaleDateString('ko-KR')}</time></div>
    <Link className="post-open" to={'/community/posts/' + encodeURIComponent(post.id)} state={{ returnTo: location.pathname + location.search }}>
          {post.kind == 'free' && <h3>{post.title}</h3>}          
          {post.book?.isbn && <div className="post-row-book-label">『{post.book.title}』</div>}
      {spoiler ? <div className="spoiler-list-preview"><div className="spoiler-blurred" aria-hidden="true"><blockquote>스포일러</blockquote></div><span className="spoiler-list-warning"><strong>스포일러 주의!</strong></span></div>
        : <>{post.quote && <blockquote>{post.quote}</blockquote>}<p className="community-excerpt">{post.body}</p></>}
    </Link>
    <div className='post-row-footer'>{post.rating ? `${'★'.repeat(post.rating)}` : ''}</div>
    {tasteReason && <small className="taste-match">{tasteReason}</small>}
    <div className="post-row-footer"><button className="author-button" disabled={!post.author.profileId} onClick={() => onAuthor?.(post.author.profileId)}>{post.author.nickname}{post.author.anonymous ? ' · 책별 가명' : ''}</button>
      <span>{post.kind !== 'line' && `추천 ${post.recommendCount} · `}댓글 {post.commentCount}{post.poll ? ' · 투표' : ''}{post.images.length ? ' · 사진' : ''}</span></div>
  </article>;
}
