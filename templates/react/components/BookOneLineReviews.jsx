import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { useLibrary } from './LibraryContext';
import { useCommunity } from './CommunityContext';
import { community } from '../communityApi';
import { invalidateBookDetail } from '../api';
import OneLineReviewList from './OneLineReviewList';
import DeleteConfirmation from './DeleteConfirmation';

export default function BookOneLineReviews({ book, onSaved }) {
  const { user } = useAuth();
  const { records, loadBookReview, recordBook, updateReview, loadingReviews, busy, notice } = useLibrary();
  const { revision, refresh } = useCommunity();
  const record = records.find(item => item.id === String(book.isbn));
  const [lines, setLines] = useState(null), [error, setError] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteFailed, setDeleteFailed] = useState(false);
  const [editing, setEditing] = useState(false), [opening, setOpening] = useState(false);
  const [message, setMessage] = useState(''), [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setError(''); setLines(null);
    community('/books/' + encodeURIComponent(book.isbn) + '/lines', { signal: controller.signal, cache: 'no-store' })
      .then(data => setLines(data.lines)).catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [book.isbn, revision, retry]);
  useEffect(() => { setEditing(false); setConfirmDelete(false); setDeleteFailed(false); setMessage(''); }, [book.isbn, user?.id]);
  async function edit() {
    setOpening(true); setMessage('');
    try { if (!record || await loadBookReview(record.id)) setEditing(true); }
    finally { setOpening(false); }
  }
  async function save(event) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const saved = await recordBook(book, { rating: Number(form.get('rating')),
      content: String(form.get('content')).trim(), hasSpoiler: false });
    if (saved) {
      invalidateBookDetail(book.isbn); setEditing(false); setMessage('한줄평을 저장했어요.'); refresh(); onSaved?.();
    }
  }
  async function deleteReview() {
    if (!record?.content || busy) return;
    setDeleteFailed(false);
    setMessage('');
    if (await updateReview(record.id, { rating: 0, content: '', hasSpoiler: false })) {
      invalidateBookDetail(book.isbn);
      setEditing(false);
      setConfirmDelete(false);
      setMessage('한줄평을 삭제했어요.');
      refresh();
      onSaved?.();
    } else {
      setDeleteFailed(true);
    }
  }
  return <section className="book-one-line-reviews"><h3>한줄평</h3>
    {error && <p role="alert">{error} <button type="button" className="text-btn" onClick={() => setRetry(n => n + 1)}>다시 불러오기</button></p>}
    {!error && (lines === null ? <p role="status">한줄평을 불러오는 중…</p>
      : lines.length ? <OneLineReviewList lines={lines} /> : <p>아직 등록된 한줄평이 없어요.</p>)}
    {user ? (!editing ? <div className="one-line-review-actions"><button type="button" className="outline-btn" disabled={opening || busy || loadingReviews} onClick={edit}>
      {opening ? '불러오는 중…' : record?.content ? '내 한줄평 수정' : '한줄평 남기기'}</button>
      {record?.content && <button type="button" className="outline-btn review-delete-btn"
        disabled={opening || busy || loadingReviews} onClick={() => {
          setDeleteFailed(false);
          setConfirmDelete(true);
        }}>내 한줄평 삭제</button>}
      </div> : <form className="editor-form" onSubmit={save}>
        <label>평점<select name="rating" required defaultValue={record?.rating || ''}>
          <option value="" disabled>평점 선택</option>{[1,2,3,4,5].map(n => <option key={n} value={n}>{'★'.repeat(n)}</option>)}
        </select></label>
        <label>한줄평<textarea name="content" rows={3} required maxLength={3000} defaultValue={record?.content || ''} /></label>
        <div><button className="primary-btn" disabled={busy}>저장</button>{' '}<button type="button" className="outline-btn" disabled={busy} onClick={() => setEditing(false)}>취소</button></div>
      </form>) : <Link to="/login">로그인하고 한줄평 남기기</Link>}
    <DeleteConfirmation open={confirmDelete} busy={busy}
      onCancel={() => setConfirmDelete(false)} onDelete={deleteReview}
      error={deleteFailed ? notice || '한줄평을 삭제하지 못했어요.' : ''} />
    <p role="status">{message || notice}</p>
  </section>;
}
