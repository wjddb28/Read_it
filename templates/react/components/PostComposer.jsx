import { useEffect, useState } from 'react';
import Modal from './Modal';
import { useAuth } from './AuthContext';
import { useLibrary } from './LibraryContext';
import { useCommunity } from './CommunityContext';
import { request } from '../api';
import { bookReference, categoryLabels, sendCommunity, stageLabels } from '../communityApi';
export default function PostComposer({ open, close, initialBook = null, initialKind = 'quote' }) {
  const { user } = useAuth();
  const { records, recordBook } = useLibrary();
  const { refresh } = useCommunity();
  const [kind, setKind] = useState(initialKind), [category, setCategory] = useState('share');
  const [book, setBook] = useState(initialBook), [title, setTitle] = useState(''), [body, setBody] = useState(''), [quote, setQuote] = useState('');
  const [rating, setRating] = useState(''), [recommended, setRecommended] = useState(''), [stage, setStage] = useState(0), [anonymous, setAnonymous] = useState(false);
  const [images, setImages] = useState([]), [pollEnabled, setPollEnabled] = useState(false), [options, setOptions] = useState(['', '']);
  const [shelfRating, setShelfRating] = useState('');
  const [saveShelf, setSaveShelf] = useState(false), [query, setQuery] = useState(''), [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [published, setPublished] = useState(null);
  useEffect(() => {
    if (!open) return;
    setKind(initialKind); setCategory(initialKind === 'free' ? 'talk' : 'share'); setBook(initialBook);
    setTitle(''); setBody(''); setQuote(''); setRating(''); setRecommended(''); setStage(0); setAnonymous(false);
    setImages([]); setPollEnabled(false); setOptions(['', '']); setSaveShelf(false); setShelfRating(''); setQuery(''); setResults([]); setMessage(''); setPublished(null);
  }, [open]);
  const shelfBook = records.find((record) => record.id === String(book?.isbn));
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
  async function saveReading() {
    const success = await recordBook(book, { review: body.trim(), rating: Number(kind !== 'line' && rating ? rating : shelfRating), hasSpoiler: Number(stage) > 0 });
    if (!success) throw new Error('글은 게시됐지만 서재 기록을 저장하지 못했어요. 아래에서 서재 저장만 다시 시도할 수 있어요.');
  }
  async function submit(event) {
    event.preventDefault(); setMessage('');
    if (!user) { setMessage('로그인 후 글을 작성할 수 있어요.'); return; }
    if (kind !== 'free' && !book) { setMessage('연결할 책을 선택해주세요.'); return; }
    if (kind === 'line' && !recommended) { setMessage('추천 여부를 선택해주세요.'); return; }
    if (saveShelf && book && !(kind !== 'line' && rating ? rating : shelfRating)) { setMessage('서재에도 감상평을 저장하려면 서재 저장용 평점을 선택해주세요.'); return; }
    setBusy(true);
    try {
      const data = await sendCommunity('/posts', { kind, category, title: title.trim(), body: body.trim(), quote: kind === 'quote' ? quote.trim() : '',
        book: book ? bookReference(book) : null, rating: kind === 'line' || !rating ? null : Number(rating),
        recommended: kind === 'line' ? recommended === 'yes' : null, stage: book ? Number(stage) : 0, anonymous: !!book && anonymous,
        images: kind === 'line' ? [] : images, poll: kind !== 'line' && pollEnabled ? options : [] });
      setPublished(data.post); refresh();
      if (saveShelf && book) await saveReading();
      close();
    } catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }
  return <Modal open={open} close={close} title={initialKind === 'line' ? '한줄평 남기기' : '책에서 시작된 이야기'}>
    {!user ? <p>로그인 후 글을 작성할 수 있어요.</p> : <form className="editor-form post-composer" onSubmit={submit}>
      {!published && <>
        <div className="composer-pair"><label>글 형식<select value={kind} onChange={(event) => setKind(event.target.value)}>
          <option value="quote">책 연결 글</option><option value="free">자유게시판</option><option value="line">한줄평</option></select></label>
          <label>카테고리<select value={category} onChange={(event) => setCategory(event.target.value)}>{Object.entries(categoryLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
        <section className="composer-book"><h3>이야기할 책 {kind === 'free' && '(선택)'}</h3>
          <label>내 서재에서 가져오기<select value={shelfBook?.id || ''} onChange={(event) => { const found = records.find((record) => record.id === event.target.value); if (found) setBook(found.book); }}>
            <option value="">서재의 책 선택</option>{records.map((record) => <option key={record.id} value={record.id}>{record.book.title}</option>)}</select></label>
          <div className="book-lookup"><input aria-label="연결할 책 검색" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="책 제목으로 검색" maxLength={200} />
            <button type="button" className="outline-btn" disabled={busy} onClick={findBooks}>책 찾기</button></div>
          {results.length > 0 && <div className="book-lookup-results">{results.map((item) => <button type="button" key={item.isbn} onClick={() => { setBook(item); setResults([]); }}>{item.title}<small>{item.author}</small></button>)}</div>}
          {book && <div className="selected-book"><strong>{book.title}</strong><span>{book.author}</span>
            <button type="button" className="text-btn" onClick={() => { setBook(null); setAnonymous(false); }}>연결 해제</button></div>}
          {shelfBook && <button type="button" className="text-btn" onClick={() => { setBody(shelfBook.review || ''); if (kind !== 'line') setRating(shelfBook.rating || ''); }}>서재의 별점·감상평 불러오기</button>}
        </section>
        {kind === 'free' && <label>제목<input required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="서평, 함께 읽기, 자유로운 책 이야기" /></label>}
        {kind === 'quote' && <label>인상 깊은 문장<textarea aria-label="인상 깊은 문장" required rows={2} maxLength={300} value={quote} onChange={(event) => setQuote(event.target.value)} placeholder="짧은 문장 하나를 나눠주세요." /></label>}
        <label>{kind === 'quote' ? '내 생각' : kind === 'line' ? '한줄평' : '내용'}<textarea aria-label="글 내용" required rows={kind === 'line' ? 2 : 4} maxLength={kind === 'line' ? 200 : kind === 'quote' ? 1000 : 3000}
          value={body} onChange={(event) => setBody(event.target.value)} placeholder={kind === 'line' ? '이 책을 추천하거나 추천하지 않는 이유를 짧게 적어주세요.' : '책을 읽고 떠오른 생각을 남겨주세요.'} /></label>
        {kind === 'line' ? <fieldset className="line-recommend"><legend>추천 여부</legend>
          <label><input type="radio" name="line-recommend" value="yes" checked={recommended === 'yes'} onChange={() => setRecommended('yes')} />추천해요</label>
          <label><input type="radio" name="line-recommend" value="no" checked={recommended === 'no'} onChange={() => setRecommended('no')} />추천하지 않아요</label></fieldset>
          : book && <label>이 책의 평점 (선택)<select value={rating} onChange={(event) => setRating(event.target.value)}><option value="">별점 없이 작성</option>{[1,2,3,4,5].map((value) => <option key={value} value={value}>{'★'.repeat(value)}</option>)}</select></label>}
        {book && <><label>진도별 스포일러 표시<select value={stage} onChange={(event) => setStage(event.target.value)}>{stageLabels.map((label, i) => <option value={i} key={label}>{label}</option>)}</select></label>
          <label className="inline-check"><input type="checkbox" checked={anonymous} onChange={(event) => setAnonymous(event.target.checked)} />책별 가명으로 게시</label>
          {anonymous && <small>같은 책에서는 같은 가명, 다른 책에서는 다른 가명을 사용해요. 익명 글은 공개 프로필·구독·취향 이웃 피드에 연결되지 않아요.</small>}
          <label className="inline-check"><input type="checkbox" checked={saveShelf} onChange={(event) => setSaveShelf(event.target.checked)} />이 글의 감상평을 내 서재에도 기록</label>
          {saveShelf && (kind === 'line' || !rating) && <label>서재 저장용 평점<select aria-label="서재 저장용 평점" value={shelfRating} onChange={(event) => setShelfRating(event.target.value)}><option value="">평점 선택</option>{[1,2,3,4,5].map((value) => <option key={value} value={value}>{'★'.repeat(value)}</option>)}</select><small>이 평점은 내 서재 리뷰에 저장돼요. 한줄평에는 추천 여부만 표시돼요.</small></label>}</>}
        {kind !== 'line' && <><label>사진 추가 (최대 3장, 각 3MB)<input aria-label="글 사진 추가" type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy}
          onChange={(event) => { const files = [...event.target.files]; event.target.value = ''; upload(files); }} /></label>
          {images.length > 0 && <div className="composer-images">{images.map((id) => <div key={id}><img src={'/api/community/media/' + id} alt="첨부할 사진" /><button type="button" onClick={() => setImages(images.filter((item) => item !== id))}>사진 제거</button></div>)}</div>}
          <label className="inline-check"><input type="checkbox" checked={pollEnabled} onChange={(event) => setPollEnabled(event.target.checked)} />투표 추가</label>
          {pollEnabled && <fieldset className="poll-editor"><legend>투표 항목</legend>{options.map((option, i) => <label key={i}>항목 {i + 1}<input required value={option} maxLength={100} onChange={(event) => setOptions(options.map((value, index) => index === i ? event.target.value : value))} /></label>)}
            <button type="button" className="outline-btn" disabled={options.length >= 6} onClick={() => setOptions([...options, ''])}>항목 추가</button>
            {options.length > 2 && <button type="button" className="text-btn" onClick={() => setOptions(options.slice(0, -1))}>마지막 항목 제거</button>}</fieldset>}</>}
        <button className="primary-btn" disabled={busy}>{busy ? '저장 중…' : '게시하기'}</button>
      </>}
      <p role="status">{message}</p>
      {published && <><p>글이 게시됐어요.</p><button type="button" className="primary-btn" disabled={busy} onClick={async () => { setBusy(true); try { await saveReading(); close(); } catch (e) { setMessage(e.message); } finally { setBusy(false); } }}>서재 저장만 다시 시도</button></>}
    </form>}
  </Modal>;
}
