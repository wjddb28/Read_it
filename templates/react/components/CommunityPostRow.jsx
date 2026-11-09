import { Link, useLocation } from 'react-router-dom';
import { categoryLabels } from '../communityApi';
export default function CommunityPostRow({ post, onAuthor }) {
  const location = useLocation();
  const spoiler = post.hasSpoiler || post.spoilerHidden;
  return <article className="community-post-row">
    <div className="post-meta"><span className={'post-category category-' + post.category}>{categoryLabels[post.category]}</span>
      {post.kind === 'line' && !post.spoilerHidden && <span className={'line-tag ' + (post.recommended ? 'is-yes' : 'is-no')}>{post.recommended ? '추천해요' : '추천하지 않아요'}</span>}
      <time>{new Date(post.createdAt).toLocaleDateString('ko-KR')}</time></div>
    <Link className="post-open" to={'/community/posts/' + encodeURIComponent(post.id)} state={{ returnTo: location.pathname + location.search }}>
      <h3>{post.title}</h3>
      {spoiler ? <div className="spoiler-list-preview"><div className="spoiler-blurred" aria-hidden="true"><blockquote>책 속의 이야기와 감상이 포함되어 있어요.</blockquote><p>내용을 확인하려면 게시글을 열어주세요.</p></div><span className="spoiler-list-warning"><strong>스포일러 주의!</strong><small>게시글을 열어 확인해주세요</small></span></div>
        : <>{post.quote && <blockquote>{post.quote}</blockquote>}<p className="community-excerpt">{post.body}</p></>}
    </Link>
    {post.book && <div className="post-book-label">『{post.book.title}』{post.rating ? ` · ${'★'.repeat(post.rating)}` : ''}</div>}
    {post.tasteMatch && <small className="taste-match">{post.tasteMatch.sharedBooks ? `같이 읽은 책 ${post.tasteMatch.sharedBooks}권` : ''} {post.tasteMatch.sharedGenres.join(' · ')}</small>}
    <div className="post-row-footer"><button className="author-button" disabled={!post.author.profileId} onClick={() => onAuthor?.(post.author.profileId)}>{post.author.nickname}{post.author.anonymous ? ' · 책별 가명' : ''}</button>
      <span>{post.kind !== 'line' && `추천 ${post.recommendCount} · `}댓글 {post.commentCount}{post.poll ? ' · 투표' : ''}{post.images.length ? ' · 사진' : ''}</span></div>
  </article>;
}
