import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Modal from './Modal';
import ProfileAvatar from './ProfileAvatar';
import { community } from '../communityApi';
export default function ReaderProfile({ profileId, close }) {
  const [data, setData] = useState(null), [error, setError] = useState('');
  useEffect(() => { if (!profileId) return; let active = true; setData(null); setError(''); community('/profiles/' + profileId).then((result) => { if (active) setData(result); }).catch((e) => { if (active) setError(e.message); }); return () => { active = false; }; }, [profileId]);
  return <Modal open={!!profileId} close={close} title="독자 프로필">{error && <p role="alert">{error}</p>}{data && <div className="reader-profile">
    <ProfileAvatar profileId={data.profile.profileId} name={data.profile.nickname} /><h3>{data.profile.nickname}</h3>{data.profile.bio && <p className="profile-bio">{data.profile.bio}</p>}
    {data.stats && <div className="profile-activity-counts" aria-label="독서 및 커뮤니티 통계">
      <span>서재 <strong>{data.stats.library.total_books}권</strong> · 완독 <strong>{data.stats.library.completed_books}권</strong></span>
      <span>총 독서 시간 <strong>{data.stats.library.total_reading_minutes}분</strong></span>
      <span>작성 글 <strong>{data.stats.community.posts}</strong> · 댓글 <strong>{data.stats.community.comments}</strong> · 한줄평 <strong>{data.stats.community.lines}</strong></span>
    </div>}
    <Link className="outline-btn" to={'/community?author=' + data.profile.profileId} onClick={close}>이 독자의 공개 글 보기</Link>
  </div>}</Modal>;
}
