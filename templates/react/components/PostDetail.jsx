import { useEffect, useState } from 'react';
import ReaderProfile from './ReaderProfile';
import { useAuth } from './AuthContext';
import { useCommunity } from './CommunityContext';
import { categoryLabels, community, sendCommunity, stageLabels } from '../communityApi';
export default function PostDetail({ postId, close }) {
  const { user } = useAuth(); const { revision, refresh } = useCommunity();
  const [data, setData] = useState(null), [error, setError] = useState(''), [reveal, setReveal] = useState(false), [body, setBody] = useState(''), [reply, setReply] = useState(null), [anonymous, setAnonymous] = useState(false), [busy, setBusy] = useState(false), [reader, setReader] = useState(null);
  useEffect(() => {
    if (!postId) return; const controller = new AbortController(); setError('');
    community('/posts/' + postId + (reveal ? '?reveal=true' : ''), { signal: controller.signal }).then(setData).catch((e) => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [postId, reveal, revision, user?.id]);
  async function action(path, value, method = 'POST') {
    setBusy(true); setError('');
    try { await sendCommunity(path, value, method); refresh(); return true; }
    catch (e) { setError(e.message); return false; } finally { setBusy(false); }
  }
  const post = data?.post;
  function renderComment(comment, nested = false) {
    return <article key={comment.id} className={'community-comment' + (nested ? ' is-reply' : '')}>
      <div><strong>{comment.author?.nickname || '삭제된 댓글'}</strong><small>{new Date(comment.createdAt).toLocaleDateString('ko-KR')}</small></div>
      <p>{comment.body}</p>
      {!comment.deleted && <div className="comment-actions">{!nested && user && <button className="text-btn" onClick={() => { setReply(comment); setBody(''); }}>답글</button>}
        {comment.own && <button className="text-btn" disabled={busy} onClick={() => { if (window.confirm('이 댓글을 삭제할까요?')) action('/comments/' + comment.id, {}, 'DELETE'); }}>삭제</button>}</div>}
      {!nested && data.comments.filter((item) => item.parentId === comment.id).map((item) => renderComment(item, true))}
    </article>;
  }
  return <><article className="board-post">{error && <p role="alert">{error}</p>}{!post && !error && <p role="status">글을 불러오는 중…</p>}{post && <div className="post-detail">
    <div className="post-meta"><span className="post-category">{categoryLabels[post.category]}</span>
      <button className="author-button" disabled={!post.author.profileId} onClick={() => setReader(post.author.profileId)}>{post.author.nickname}{post.author.anonymous ? ' · 책별 가명' : ''}</button>
      <time>{new Date(post.createdAt).toLocaleString('ko-KR')}</time></div>
    <h1>{post.title}</h1>{(post.hasSpoiler || post.spoilerHidden) && <p className="post-spoiler-notice">스포일러 주의! 줄거리나 결말이 포함된 글이에요.</p>}{post.book && <div className="post-book-label">『{post.book.title}』 · {stageLabels[post.stage]}</div>}
    {post.spoilerHidden ? <div className="spoiler-gate"><strong>스포일러 주의!</strong><p>{post.hasSpoiler ? '작성자가 스포일러를 표시한 글이에요. 내용을 보시겠어요?' : '내 독서 진도보다 뒤쪽 내용이라 가려두었어요.'}</p><button className="outline-btn" onClick={() => setReveal(true)}>스포일러 확인하고 보기</button></div>
      : <>{post.quote && <blockquote>{post.quote}</blockquote>}<p className="post-body">{post.body}</p>
        {post.rating && <p className="stars">{'★'.repeat(post.rating)}{'☆'.repeat(5-post.rating)}</p>}
        {post.kind === 'line' && <p className="line-verdict">{post.recommended ? '추천해요' : '추천하지 않아요'}</p>}
        {post.images.length > 0 && <div className="post-images">{post.images.map((image) => <img key={image.id} src={'/api/community/media/' + image.id + (reveal ? '?reveal=true' : '')} alt="게시물 첨부 사진" />)}</div>}
        {post.poll && <section className="post-poll"><h4>함께 골라봐요 · {post.poll.total}명 참여</h4>{post.poll.options.map((option) => <button type="button" key={option.id} disabled={busy || !user} aria-pressed={post.poll.myVote === option.id}
          onClick={() => action('/posts/' + post.id + '/vote', { optionId: option.id })}><span>{option.label}</span><strong>{option.votes}표</strong><span className="poll-fill" style={{ width: (post.poll.total ? option.votes / post.poll.total * 100 : 0) + '%' }} /></button>)}</section>}
        <div className="post-actions">{post.kind !== 'line' && <button className="outline-btn" disabled={!user || busy || post.own} aria-pressed={post.recommendedByMe} onClick={() => action('/posts/' + post.id + '/recommend', {})}>추천 {post.recommendCount}</button>}
          {post.own && <button className="text-btn" disabled={busy} onClick={async () => { if (window.confirm('이 글을 삭제할까요?') && await action('/posts/' + post.id, {}, 'DELETE')) close(); }}>글 삭제</button>}</div>
        <section className="post-comments"><h4>댓글 {post.commentCount}</h4>{data.comments.filter((item) => !item.parentId).map((item) => renderComment(item))}
          {user ? <form className="editor-form" onSubmit={async (event) => { event.preventDefault(); if (await action('/posts/' + post.id + '/comments', { body, parentId: reply?.id || null, anonymous })) { setBody(''); setReply(null); } }}>
            {reply && <p>{reply.author?.nickname || '독자'}님에게 답글 <button type="button" className="text-btn" onClick={() => setReply(null)}>취소</button></p>}
            <label>{reply ? '대댓글' : '댓글'}<textarea aria-label="댓글 내용" required value={body} rows={3} maxLength={1000} onChange={(event) => setBody(event.target.value)} /></label>
            {post.book && <label className="inline-check"><input type="checkbox" checked={anonymous || (post.own && post.author.anonymous)} disabled={post.own && post.author.anonymous} onChange={(event) => setAnonymous(event.target.checked)} />책별 가명으로 댓글</label>}
            <button className="primary-btn" disabled={busy}>{reply ? '대댓글 등록' : '댓글 등록'}</button></form> : <p>로그인하면 댓글을 남길 수 있어요.</p>}
        </section></>}
  </div>}</article><ReaderProfile profileId={reader} close={() => setReader(null)} /></>;
}
