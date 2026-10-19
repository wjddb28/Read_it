import { createContext, useContext, useEffect, useRef, useState } from "react";
import { request } from "../api";
const Context = createContext(null);
const PROFILE_PREFIX = "readit.profile.v1:";
function readProfile(id) {
  try {
    const profile = JSON.parse(localStorage.getItem(PROFILE_PREFIX + id) || "null");
    if (!profile || typeof profile !== "object") return {};
    const nickname = typeof profile.nickname === "string" ? profile.nickname.trim() : "";
    return { ...(nickname.length >= 2 && nickname.length <= 20 ? { nickname } : {}),
      bio: typeof profile.bio === "string" ? profile.bio.slice(0, 200) : "" };
  } catch { return {}; }
}
export function AuthProvider({ children }) {
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [, setProfileVersion] = useState(0);
  const owner = useRef(null);
  owner.current = account?.id;
  const user = account ? { ...account, ...readProfile(account.id) } : null;
  useEffect(() => {
    let active = true;
    request("/api/auth/me").then((data) => {
      if (active) setAccount(data.user);
    }).catch((e) => {
      if (active && e.status !== 401) setError(e.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const sync = (event) => {
      if (event.key === PROFILE_PREFIX + account?.id || event.key === null)
        setProfileVersion((version) => version + 1);
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, [account?.id]);
  async function login(path, payload) {
    const data = await request("/api/auth/" + path, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    setAccount(data.user);
    setError("");
  }
  async function logout() {
    await request("/api/auth/logout", { method: "POST" });
    owner.current = null;
    setAccount(null);
  }
  async function updateProfile({ nickname, bio }) {
    const id = account?.id;
    if (!id) throw new Error("로그인 후 내 정보를 수정할 수 있어요.");
    nickname = String(nickname || "").trim();
    bio = String(bio || "").trim();
    if (nickname.length < 2 || nickname.length > 20) throw new Error("닉네임은 2~20자로 입력해주세요.");
    if (bio.length > 200) throw new Error("소개는 200자까지 적을 수 있어요.");
    try {
      const session = await request("/api/auth/me");
      if (session.user.id !== id || owner.current !== id) throw new Error("계정이 변경됐어요. 다시 로그인해주세요.");
      localStorage.setItem(PROFILE_PREFIX + id, JSON.stringify({ nickname, bio }));
      setProfileVersion((version) => version + 1);
      return true;
    } catch (e) {
      if (e.status === 401) { owner.current = null; setAccount(null); }
      throw e;
    }
  }
  return <Context.Provider value={{ user, loading, error, login, logout, updateProfile,
    invalidate: () => { owner.current = null; setAccount(null); } }}>{children}</Context.Provider>;
}
export const useAuth = () => useContext(Context);
