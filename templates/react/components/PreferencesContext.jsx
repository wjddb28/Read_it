import { createContext, useContext, useEffect, useState } from "react";
import { useAuth } from "./AuthContext";
const Context = createContext(null);
const PREFIX = "readit.preferences.v1:";
function load(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return typeof value?.aiComments === "boolean" ? value.aiComments : true;
  } catch { return true; }
}
export function PreferencesProvider({ children }) {
  const { user, loading } = useAuth();
  const key = PREFIX + (user?.id || "guest");
  const [state, setState] = useState(() => ({ key, aiComments: load(key) }));
  const [preferenceMessage, setMessage] = useState("");
  const aiComments = state.key === key ? state.aiComments : load(key);
  useEffect(() => {
    setState({ key, aiComments: load(key) }); setMessage("");
    const sync = (event) => {
      if (event.key === key || event.key === null) setState({ key, aiComments: load(key) });
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, [key]);
  function changeAIComments(value) {
    setState({ key, aiComments: value });
    try {
      localStorage.setItem(key, JSON.stringify({ aiComments: value }));
      setMessage(value ? "AI 추천 코멘트 받기를 켰어요." : "AI 추천 코멘트 받기를 껐어요.");
    } catch { setMessage("현재 화면에 적용했어요. 브라우저 저장이 제한되어 새로고침하면 유지되지 않을 수 있어요."); }
  }
  return <Context.Provider value={{ aiComments, changeAIComments, preferenceMessage, preferencesReady: !loading }}>{children}</Context.Provider>;
}
export const usePreferences = () => useContext(Context);
