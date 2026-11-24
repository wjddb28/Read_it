import { createContext, useContext, useEffect, useState } from "react";
import { useAuth } from "./AuthContext";

const Context = createContext(null);
const PREFIX = "readit.preferences.v1:";

function load(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return { aiComments: value?.aiComments !== false, anonymousPosts: value?.anonymousPosts === true };
  } catch {
    return { aiComments: true, anonymousPosts: false };
  }
}

export function PreferencesProvider({ children }) {
  const { user, loading } = useAuth();
  const key = PREFIX + (user?.id || "guest");
  const [state, setState] = useState(() => ({ key, values: load(key) }));
  const [preferenceMessage, setMessage] = useState("");
  const values = state.key === key ? state.values : load(key);

  useEffect(() => {
    const sync = () => setState({ key, values: load(key) });
    sync();
    setMessage("");
    const onStorage = (event) => {
      if (event.key === key || event.key === null) sync();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [key]);

  function save(patch) {
    const next = { ...values, ...patch };
    setState({ key, values: next });
    try {
      localStorage.setItem(key, JSON.stringify(next));
      setMessage("");
    } catch {
      setMessage("현재 화면에 적용했어요. 새로고침하면 설정이 유지되지 않을 수 있어요.");
    }
  }

  return <Context.Provider value={{
    ...values,
    changeAIComments: (aiComments) => save({ aiComments }),
    changeAnonymousPosts: (anonymousPosts) => save({ anonymousPosts }),
    preferenceMessage,
    preferencesReady: !loading,
  }}>{children}</Context.Provider>;
}

export const usePreferences = () => useContext(Context);
