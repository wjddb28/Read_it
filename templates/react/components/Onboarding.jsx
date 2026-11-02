import { useEffect, useRef, useState } from 'react';
import { useAuth } from './AuthContext';
import GenrePicker from './GenrePicker';
export default function Onboarding() {
  const { user, updateProfile } = useAuth();
  const dialog = useRef(null);
  const needed = !!user && user.communityReady && user.onboarded === false;
  const [step, setStep] = useState(0), [nickname, setNickname] = useState('');
  const [liked, setLiked] = useState([]), [disliked, setDisliked] = useState([]), [message, setMessage] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { setStep(0); setNickname(user?.nickname || ''); setLiked(user?.likedGenres || []); setDisliked(user?.dislikedGenres || []); setMessage(''); }, [user?.id]);
  useEffect(() => {
    if (needed && dialog.current && !dialog.current.open) dialog.current.showModal();
    if (!needed && dialog.current?.open) dialog.current.close();
  }, [needed]);
  if (!needed) return null;
  async function finish(skip = false) {
    if (nickname.trim().length < 2 || nickname.trim().length > 20) { setStep(0); setMessage('닉네임은 2~20자로 입력해주세요.'); return; }
    if (!skip && liked.length < 3) { setMessage('좋아하는 장르를 3개 이상 선택하거나 취향은 나중에 설정해주세요.'); return; }
    setBusy(true); setMessage('');
    try { await updateProfile({ nickname: nickname.trim(), likedGenres: skip ? [] : liked, dislikedGenres: skip ? [] : disliked, onboarded: true }); }
    catch (e) { setMessage(e.message); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="onboarding-card" aria-labelledby="onboarding-title" onCancel={(event) => event.preventDefault()}>
    <p className="section-kicker">READ-IT 시작하기 · {step + 1} / 2</p>
    <h1 id="onboarding-title">{step ? '어떤 책을 좋아하세요?' : '어떤 이름으로 만날까요?'}</h1>
    <p>{step ? '좋아하는 장르로 첫 추천을 준비해드려요. 피하고 싶은 장르는 선택 사항이에요.' : '커뮤니티에서 사용할 닉네임을 정해주세요.'}</p>
    {step === 0 ? <label className="onboarding-name">닉네임<input aria-label="처음 사용할 닉네임" value={nickname} maxLength={20} onChange={(event) => setNickname(event.target.value)} autoComplete="nickname" /></label>
      : <><GenrePicker label="선호하는 장르" value={liked} onChange={setLiked} excluded={disliked} />
        <GenrePicker label="비선호하는 장르" value={disliked} onChange={setDisliked} excluded={liked} /></>}
    <p role="alert">{message}</p>
    <div className="onboarding-actions">{step === 0 ? <button className="primary-btn" onClick={() => {
      if (nickname.trim().length < 2) setMessage('닉네임은 2~20자로 입력해주세요.'); else { setStep(1); setMessage(''); }
    }}>다음</button> : <><button className="outline-btn" disabled={busy} onClick={() => setStep(0)}>이전</button>
      <button className="text-btn" disabled={busy} onClick={() => finish(true)}>취향은 나중에</button>
      <button className="primary-btn" disabled={busy} onClick={() => finish(false)}>{busy ? '저장 중…' : '시작하기'}</button></>}</div>
  </dialog>;
}
