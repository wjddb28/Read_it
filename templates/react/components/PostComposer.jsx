import { useEffect, useState } from 'react';
import Modal from './Modal';
import { usePreferences } from './PreferencesContext';
import { useAuth } from './AuthContext';
import { useLibrary } from './LibraryContext';
import { useCommunity } from './CommunityContext';
import { request } from '../api';
import { bookReference, categoryLabels, sendCommunity, stageLabels } from '../communityApi';
export default function PostComposer({ open, close, initialBook = null, initialKind = 'quote', post = null }) {
  const { user } = useAuth();
  const { anonymousPosts } = usePreferences();
  const { records } = useLibrary();
  const { refresh } = useCommunity();
  const [kind, setKind] = useState(initialKind === 'free' ? 'free' : 'quote'), [category, setCategory] = useState('share');
  const [book, setBook] = useState(initialBook), [title, setTitle] = useState(''), [body, setBody] = useState(''), [quote, setQuote] = useState('');
  const [rating, setRating] = useState(''), [stage, setStage] = useState(0);
  const [images, setImages] = useState([]), [pollEnabled, setPollEnabled] = useState(false), [options, setOptions] = useState(['', '']);
  const [hasSpoiler, setHasSpoiler] = useState(false);
  const [attachedReviewIsbn, setAttachedReviewIsbn] = useState(null);
  const [query, setQuery] = useState(''), [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [published, setPublished] = useState(null);
  useEffect(() => {
    if (!open) return;
    setHasSpoiler(Boolean(post?.hasSpoiler)); setAttachedReviewIsbn(null); setKind(post?.kind || (initialKind === 'free' ? 'free' : 'quote'));
    setCategory(post?.category || (initialKind === 'free' ? 'talk' : 'share')); setBook(post?.book?.isbn ? post.book : initialBook);
    setTitle(post?.title || ''); setBody(post?.body || ''); setQuote(post?.quote || '');
    setRating(post?.rating == null ? '' : String(post.rating)); setStage(post?.stage ?? 0);
    setImages(post?.images?.map((image) => image.id) || []);
    setPollEnabled(Boolean(post?.poll)); setOptions(post?.poll?.options.map((option) => option.label) || ['', '']);
    setQuery(''); setResults([]); setMessage(''); setPublished(null);
  }, [open, post, initialBook, initialKind]);
  const editing = Boolean(post);
  const shelfBook = records.find((record) => record.id === String(book?.isbn));
  const attachedReview = !!shelfBook?.review?.trim() && attachedReviewIsbn === shelfBook.id;
  async function findBooks() {
    if (!query.trim()) return;
    setBusy(true); setMessage('');
    try { const data = await request('/api/catalog/search?' + new URLSearchParams({ q: query.trim(), by: 'title', sort: 'popular', page: '1' })); setResults(data.books || []); }
    catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }
  async function upload(files) {
    if (images.length + files.length > 3) { setMessage('사진은 3장까지 첨부할 수 있어요.'); return; }
    setBusy(true); setMessage('');
    try {
      for (const file of files) {
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 3 * 1024 * 1024) throw new Error('3MB 이하의 JPG·PNG·WebP 사진을 선택해주세요.');
        const data = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('사진을 읽지 못했어요.')); reader.readAsDataURL(file); });
        const image = await sendCommunity('/images', { data }); setImages((previous) => [...previous, image.id]);
      }
    } catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }
  async function submit(event) {
    event.preventDefault(); setMessage('');
    if (!user) { setMessage('로그인이 필요해요.'); return; }
    if (kind !== 'free' && !book) { setMessage('연결할 책을 선택해주세요.'); return; }
    setBusy(true);
    try {
      const payload = { kind, category: kind === 'free' ? category : 'share', title: title.trim(), body: body.trim(), quote: editing ? quote.trim() : kind === 'quote' ? quote.trim() : '',
        book: book ? bookReference(book) : null, attachReview: editing ? false : attachedReview, rating: !rating ? null : Number(rating),
        recommended: editing ? post.recommended : null, hasSpoiler, stage: book ? Number(stage) : 0, anonymous: editing ? Boolean(post.author?.anonymous) : anonymousPosts,
        images, poll: pollEnabled ? options : [] };
      if (editing) await sendCommunity('/posts/' + post.id + '/update', payload, 'PUT');
      else {
        const data = await sendCommunity('/posts', payload);
        setPublished(data.post);
      }
      refresh();
      close();
    } catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }
  return <Modal open={open} close={close} title={editing ? '커뮤니티 글 수정' : '커뮤니티 글쓰기'} size="composer">
    {!user ? <p>로그인이 필요해요.</p> : <form className="editor-form post-composer" onSubmit={submit}>
      {!published && <>
        <div className="composer-pair"><label>글 형식<select value={kind} disabled={editing} onChange={(event) => setKind(event.target.value)}>
          <option value="quote">서평</option><option value="free">자유게시판</option>{kind === 'line' && <option value="line">한줄평</option>}</select></label>
          {kind === 'free' && <label>주제<select value={category} disabled={editing} onChange={(event) => setCategory(event.target.value)}>{Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}</div>
        <section className="composer-book"><h3>이야기할 책 {kind === 'free' && '(선택)'}</h3>
          {editing ? <><div className="selected-book">{book ? <><strong>{book.title}</strong><span>{book.author}</span></> : <strong>연결된 책 없음</strong>}</div>
            <p role="note">게시글을 수정할 때는 책 연결을 변경할 수 없어요.</p></>
            : <>
              <label>내 서재에서 가져오기<select value={shelfBook?.id || ''} onChange={(event) => { const found = records.find((record) => record.id === event.target.value); if (found) { setBook(found.book); setAttachedReviewIsbn(null); } }}>
                <option value="">서재의 책 선택</option>{records.map((record) => <option key={record.id} value={record.id}>{record.book.title}</option>)}</select></label>
              <div className="book-lookup"><input aria-label="연결할 책 검색" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="책 제목으로 검색" maxLength={200} />
                <button type="button" className="outline-btn" disabled={busy} onClick={findBooks}>책 찾기</button></div>
              {results.length > 0 && <div className="book-lookup-results">{results.map((item) => <button type="button" key={item.isbn} onClick={() => { setBook(item); setAttachedReviewIsbn(null); setResults([]); }}>{item.title}<small>{item.author}</small></button>)}</div>}
              {book && <div className="selected-book"><strong>{book.title}</strong><span>{book.author}</span>
                <button type="button" className="text-btn" onClick={() => { setBook(null); setAttachedReviewIsbn(null); }}>연결 해제</button></div>}
              {shelfBook?.review?.trim() && (attachedReview
                ? <div className="linked-one-line-review">
                    <strong>내 한줄평</strong><blockquote>{shelfBook.review}</blockquote>
                    <button type="button" className="text-btn" onClick={() => setAttachedReviewIsbn(null)}>한줄평 연결 해제</button>
                  </div>
                : <button type="button" className="text-btn" onClick={() => setAttachedReviewIsbn(shelfBook.id)}>서재의 한줄평 연결</button>)}
            </>}
        </section>
        {kind === 'free' && <label>제목<input required maxLength={100} value={title} onChange={(event) => setTitle(event.target.value)} /></label>}
        {(kind === 'quote' || (editing && kind === 'line')) && <label>인상 깊은 문장 (선택)<textarea aria-label="인상 깊은 문장" rows={2} maxLength={300} value={quote} onChange={(event) => setQuote(event.target.value)} /></label>}
        <label>{kind === 'quote' ? '서평' : '내용'}<textarea aria-label="글 내용" required={!attachedReview} rows={8} maxLength={kind === 'quote' ? 1000 : 3000}
          value={body} onChange={(event) => setBody(event.target.value)} /></label>
        {book && <label>이 책의 평점 (선택)<select value={rating} onChange={(event) => setRating(event.target.value)}><option value="">별점 없이 작성</option>{[1,2,3,4,5].map((value) => <option key={value} value={value}>{'★'.repeat(value)}</option>)}</select></label>}
        <section className="composer-spoiler-setting" aria-label="스포일러 설정"><button type="button" className="spoiler-toggle" aria-pressed={hasSpoiler} onClick={() => setHasSpoiler(!hasSpoiler)}>{hasSpoiler ? '✓ 스포일러 포함' : '스포일러 표시'}</button></section>
        <details className="composer-extras"><summary>추가 옵션</summary><div className="composer-extras-content">
          {book && <label>진도별 스포일러 표시<select value={stage} onChange={(event) => setStage(event.target.value)}>{stageLabels.map((label, i) => <option value={i} key={label}>{label}</option>)}</select></label>}
        <><label>사진 추가 (최대 3장, 각 3MB)<input aria-label="글 사진 추가" type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy}
          onChange={(event) => { const files = [...event.target.files]; event.target.value = ''; upload(files); }} /></label>
          {images.length > 0 && <div className="composer-images">{images.map((id) => <div key={id}><img src={'/api/community/media/' + id} alt="첨부할 사진" /><button type="button" onClick={() => setImages(images.filter((item) => item !== id))}>사진 제거</button></div>)}</div>}
          <label className="inline-check"><input type="checkbox" checked={pollEnabled} onChange={(event) => setPollEnabled(event.target.checked)} />{editing && post.poll ? '투표 유지' : '투표 추가'}</label>
          {editing && post.poll && <p role="note">기존 투표는 선택지 수를 바꿀 수 없고 문구만 수정할 수 있어요. 투표를 삭제하면 참여 기록도 함께 삭제돼요.</p>}
          {pollEnabled && <fieldset className="poll-editor"><legend>투표 항목</legend>{options.map((option, i) => <label key={i}>항목 {i + 1}<input required value={option} maxLength={100} onChange={(event) => setOptions(options.map((value, index) => index === i ? event.target.value : value))} /></label>)}
            {!(editing && post.poll) && <><button type="button" className="outline-btn" disabled={options.length >= 6} onClick={() => setOptions([...options, ''])}>항목 추가</button>
              {options.length > 2 && <button type="button" className="text-btn" onClick={() => setOptions(options.slice(0, -1))}>마지막 항목 제거</button>}</>}</fieldset>}</>
        </div></details>
        <div className="composer-actions"><button type="button" className="outline-btn" disabled={busy} onClick={close}>취소</button><button className="primary-btn" disabled={busy}>{busy ? '저장 중…' : editing ? '저장하기' : '게시하기'}</button></div>
      </>}
      <p role="status">{message}</p>

    </form>}
  </Modal>;
}
