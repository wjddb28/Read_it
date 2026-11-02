import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from './AuthContext';
import { useLibrary } from './LibraryContext';
import { bookReference, sendCommunity } from '../communityApi';
const Context = createContext(null);
export function CommunityProvider({ children }) {
  const { user } = useAuth();
  const { records, ready } = useLibrary();
  const [revision, setRevision] = useState(0), [progress, setProgress] = useState({}), [syncError, setSyncError] = useState('');
  const signature = JSON.stringify(records.map((record) => ({ book: bookReference(record.book), rating: record.rating || 0, status: record.status })));
  useEffect(() => {
    if (!user || !user.communityReady || !ready) { setProgress({}); return; }
    let active = true; setSyncError('');
    sendCommunity('/reading-sync', { records: JSON.parse(signature) }).then((data) => { if (active) { setProgress(data.progress); setRevision((n) => n + 1); } })
      .catch((e) => { if (active) setSyncError(e.message); });
    return () => { active = false; };
  }, [user?.id, user?.communityReady, ready, signature]);
  async function setReadingProgress(isbn, value) {
    await sendCommunity('/progress/' + encodeURIComponent(isbn), { progress: Number(value) }, 'PUT');
    setProgress((current) => ({ ...current, [isbn]: Number(value) }));
    setRevision((number) => number + 1);
  }
  const value = useMemo(() => ({ revision, refresh: () => setRevision((n) => n + 1), progress, setReadingProgress, syncError }), [revision, progress, syncError]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export const useCommunity = () => useContext(Context);
