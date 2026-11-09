import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Modal from './Modal';
import { useAuth } from './AuthContext';
import { useCommunity } from './CommunityContext';
import { community, sendCommunity } from '../communityApi';
export default function ReaderProfile({ profileId, close }) {
  const { user } = useAuth(); const { refresh } = useCommunity();
  const [data, setData] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { if (!profileId) return; let active = true; setData(null); setError(''); community('/profiles/' + profileId).then((result) => { if (active) setData(result); }).catch((e) => { if (active) setError(e.message); }); return () => { active = false; }; }, [profileId]);
  return <Modal open={!!profileId} close={close} title="독자 프로필">{error && <p role="alert">{error}</p>}{data && <div className="reader-profile">
    <div className="profile-avatar">{data.profile.nickname.slice(0,1)}</div><h3>{data.profile.nickname}</h3><p className="profile-bio">{data.profile.bio || '아직 소개가 없어요.'}</p>
    <Link className="outline-btn" to={'/community?author=' + data.profile.profileId} onClick={close}>이 독자의 공개 글 보기</Link>
    {user && !data.own && <button className="primary-btn" disabled={busy} onClick={async () => { setBusy(true); try { const result = await sendCommunity('/profiles/' + profileId + '/follow', {}); setData({ ...data, following: result.following }); refresh(); } catch (e) { setError(e.message); } finally { setBusy(false); } }}>{data.following ? '팔로우 취소' : '팔로우하기'}</button>}
    <small>구독해도 상대에게 알림이 가지 않으며, 구독자 수는 표시하지 않아요.</small>
  </div>}</Modal>;
}
