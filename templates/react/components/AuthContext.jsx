import { createContext, useContext, useEffect, useRef, useState } from "react";
import { getProfile, request, saveProfile } from "../api";
const Context = createContext(null);

export function AuthProvider({ children }) {
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [profileState, setProfileState] = useState({ owner: null, data: null });
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState("");
  const owner = useRef(null);
  owner.current = account?.id;
  const profile = profileState.owner === account?.id ? profileState.data : null;
  const user = account
    ? {
        ...account,
        ...(profile
          ? {
              nickname: profile.nickname,
              bio: profile.about_me || "",
              stats: profile.stats,
              gender: profile.gender,
              birth_year: profile.birth_year,
            }
          : {}),
      }
    : null;

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
    let active = true;
    const userId = account?.id;
    if (!userId) {
      setProfileState({ owner: null, data: null });
      setProfileLoading(false);
      setProfileError("");
      return () => { active = false; };
    }

    setProfileState({ owner: userId, data: null });
    setProfileLoading(true);
    setProfileError("");
    getProfile().then((data) => {
      if (active && owner.current === userId)
        setProfileState({ owner: userId, data });
    }).catch((e) => {
      if (!active || owner.current !== userId) return;
      if (e.status === 401) {
        owner.current = null;
        setAccount(null);
      } else {
        setProfileError(e.message);
      }
    }).finally(() => {
      if (active) setProfileLoading(false);
    });
    return () => { active = false; };
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

  async function updateProfile({ nickname, bio, gender, birth_year }) {
    const id = account?.id;
    if (!id) throw new Error("로그인 후 내 정보를 수정할 수 있어요.");
    nickname = String(nickname || "").trim();
    bio = String(bio || "").trim();
    gender = String(gender || "").trim();
    birth_year = Number(birth_year || 0);
    if (nickname.length < 2 || nickname.length > 20) throw new Error("닉네임은 2~20자로 입력해주세요.");
    if (bio.length > 200) throw new Error("소개는 200자까지 적을 수 있어요.");
    try {
      const session = await request("/api/auth/me");
      if (session.user.id !== id || owner.current !== id)
        throw new Error("계정이 변경됐어요. 다시 로그인해주세요.");
      const data = await saveProfile({ nickname, bio, gender, birth_year });
      if (owner.current !== id) throw new Error("계정이 변경됐어요. 다시 로그인해주세요.");
      setProfileState({ owner: id, data });
      setProfileError("");
      return true;
    } catch (e) {
      if (e.status === 401) { owner.current = null; setAccount(null); }
      throw e;
    }
  }

  return <Context.Provider value={{
    user, loading, error, profileLoading, profileError, login, logout, updateProfile,
    invalidate: () => { owner.current = null; setAccount(null); },
  }}>{children}</Context.Provider>;
}

export const useAuth = () => useContext(Context);
