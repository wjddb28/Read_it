import { createContext, useContext, useMemo, useState } from 'react';
import { useAuth } from './AuthContext';
import { useLibrary } from './LibraryContext';
import { sendCommunity } from '../communityApi';
const Context = createContext(null);
export function CommunityProvider({ children }) {
  const { user } = useAuth();
  const { records } = useLibrary();
  const [revision, setRevision] = useState(0), [progressByUser, setProgressByUser] = useState({});
  const progressOverrides = progressByUser[user?.id] || {};
  const progress = useMemo(() => ({
    ...Object.fromEntries(records.map((record) => [
      record.id,
      record.status === 'COMPLETED' ? 2 : ({ EARLY: 0, MID: 1, LATE: 2 }[record.progress] ?? 0),
    ])),
    ...progressOverrides,
  }), [records, progressOverrides]);
  async function setReadingProgress(isbn, value) {
    const nextProgress = Number(value);
    await sendCommunity('/progress/' + encodeURIComponent(isbn), { progress: nextProgress }, 'PUT');
    setProgressByUser((current) => ({
      ...current,
      [user.id]: { ...(current[user.id] || {}), [isbn]: nextProgress },
    }));
    setRevision((number) => number + 1);
  }
  const value = useMemo(() => ({ revision, refresh: () => setRevision((n) => n + 1), progress, setReadingProgress }), [revision, progress]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export const useCommunity = () => useContext(Context);
