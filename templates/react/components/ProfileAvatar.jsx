import { useEffect, useState } from 'react';

export default function ProfileAvatar({ profileId, name, refreshKey = 0, small = false }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [profileId, refreshKey]);
  const initial = (name || '독자').slice(0, 1);
  return <div className={'profile-avatar' + (small ? ' profile-avatar-small' : '')} role="img" aria-label={`${name || '독자'} 프로필 사진`}>
    {!failed && profileId && <img
      src={`/api/community/pfp/${encodeURIComponent(profileId)}?v=${refreshKey}`}
      alt=""
      onError={() => setFailed(true)}
    />}
    <span>{initial}</span>
  </div>;
}
