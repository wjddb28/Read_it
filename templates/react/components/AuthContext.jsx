import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { request } from '../api';
import { community, sendCommunity } from '../communityApi';
const Context = createContext(null);
function legacy(id) {
  try { return JSON.parse(localStorage.getItem('readit.profile.v1:' + id) || '{}'); } catch { return {}; }
}
async function hydrate(account) {
  try {
    const { profile } = await community('/me');
    const saved = legacy(account.id);
    return { ...account, ...profile, nickname: profile.onboarded ? profile.nickname : saved.nickname || account.nickname,
      bio: profile.onboarded ? profile.bio : saved.bio || '', communityReady: true };
  } catch {
    return { ...account, ...legacy(account.id), communityReady: false };
  }
}
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null), [loading, setLoading] = useState(true), [error, setError] = useState('');
  const owner = useRef(null);
  useEffect(() => {
    let active = true;
    request('/api/auth/me').then(async ({ user: account }) => {
      const next = await hydrate(account);
      if (active) { owner.current = next.id; setUser(next); }
    }).catch((e) => { if (active && e.status !== 401) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function login(path, payload) {
    const { user: account } = await request('/api/auth/' + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const next = await hydrate(account); owner.current = next.id; setUser(next); setError('');
  }
  async function logout() { await request('/api/auth/logout', { method: 'POST' }); owner.current = null; setUser(null); }
  async function updateProfile(patch) {
    if (!user) throw new Error('로그인 후 내 정보를 수정할 수 있어요.');
    const id = user.id;
    const { profile } = await sendCommunity('/me', { nickname: user.nickname, bio: user.bio || '',
      likedGenres: user.likedGenres || [], dislikedGenres: user.dislikedGenres || [], onboarded: true, ...patch }, 'PUT');
    if (owner.current !== id) throw new Error('계정이 변경됐어요. 다시 로그인해주세요.');
    setUser((current) => current?.id === id ? { ...current, ...profile, communityReady: true } : current);
    return true;
  }
  return <Context.Provider value={{ user, loading, error, login, logout, updateProfile,
    invalidate: () => { owner.current = null; setUser(null); } }}>{children}</Context.Provider>;
}
export const useAuth = () => useContext(Context);
