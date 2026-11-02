import { categoryLabels, stageLabels } from '../communityApi';
export default function CommunityPostRow({ post, onOpen, onAuthor }) {
  return <article className="community-post-row">
    <div className="post-meta"><span className={'post-category category-' + post.category}>{categoryLabels[post.category]}</span>
      {post.kind === 'line' && !post.spoilerHidden && <span className={'line-tag ' + (post.recommended ? 'is-yes' : 'is-no')}>{post.recommended ? '추천해요' : '추천하지 않아요'}</span>}
      <time>{new Date(post.createdAt).toLocaleDateString('ko-KR')}</time></div>
    <button className="post-open" onClick={() => onOpen(post.id)}>
      <h3>{post.title}</h3>
      {post.spoilerHidden ? <p className="spoiler-preview">{stageLabels[post.stage]} 스포일러 · 눌러서 확인할 수 있어요.</p>
        : <>{post.quote && <blockquote>{post.quote}</blockquote>}<p className="community-excerpt">{post.body}</p></>}
    </button>
    {post.book && <div className="post-book-label">『{post.book.title}』{post.rating ? ` · ${'★'.repeat(post.rating)}` : ''}</div>}
    {post.tasteMatch && <small className="taste-match">{post.tasteMatch.sharedBooks ? `같이 읽은 책 ${post.tasteMatch.sharedBooks}권` : ''} {post.tasteMatch.sharedGenres.join(' · ')}</small>}
    <div className="post-row-footer"><button className="author-button" disabled={!post.author.profileId} onClick={() => onAuthor?.(post.author.profileId)}>{post.author.nickname}{post.author.anonymous ? ' · 책별 가명' : ''}</button>
      <span>{post.kind !== 'line' && `추천 ${post.recommendCount} · `}댓글 {post.commentCount}{post.poll ? ' · 투표' : ''}{post.images.length ? ' · 사진' : ''}</span></div>
  </article>;
}
