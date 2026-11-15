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
  const owner = useRef(null), saving = useRef(false);
  owner.current = account?.id;
  const state = profileState.owner === account?.id ? profileState : null;
  const profile = state?.data;
  const profilesPending = !!account && (profileState.owner !== account.id || profileLoading);
  const user = account ? {
    id: account.id, email: account.email, ...(profile || {}),
    nickname: profile?.nickname || "독자",
    bio: profile?.about_me || "",
    likedGenres: profile?.likedGenres || [], dislikedGenres: profile?.dislikedGenres || [],
    gender: profile?.gender ?? null, birth_year: profile?.birth_year ?? null,
    communityReady: !!profile,
  } : null;

  function invalidate() {
    owner.current = null;
    setAccount(null);
    setProfileState({ owner: null, data: null });
  }
  useEffect(() => {
    let active = true;
    request("/api/auth/me").then(({ user }) => { if (active) setAccount(user); })
      .catch((e) => { if (active && e.status !== 401) setError(e.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    const id = account?.id;
    setProfileState({ owner: id || null, data: null });
    setProfileError("");
    if (!id) {
      setProfileLoading(false);
      return () => { active = false; };
    }
    setProfileLoading(true);
    getProfile().then((data) => {
      if (!active || owner.current !== id) return;
      setProfileState({ owner: id, data });
      setProfileError("");
    }).catch((e) => {
      if (!active || owner.current !== id) return;
      if (e.status === 401) { invalidate(); return; }
      setProfileError(e.message);
    }).finally(() => { if (active && owner.current === id) setProfileLoading(false); });
    return () => { active = false; };
  }, [account?.id]);

  async function login(path, payload) {
    const { user } = await request("/api/auth/" + path, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    owner.current = user.id; setAccount(user); setError("");
  }
  async function logout() {
    await request("/api/auth/logout", { method: "POST" });
    invalidate();
  }
  async function updateProfile(patch) {
    const id = user?.id;
    if (!id) throw new Error("로그인 후 내 정보를 수정할 수 있어요.");
    if (profilesPending || !profile) throw new Error("기본 프로필을 불러온 뒤 저장해주세요. 서버 연결을 확인해주세요.");
    if (saving.current) throw new Error("프로필을 저장 중이에요. 잠시만 기다려주세요.");
    const next = { ...user, ...patch };
    const nickname = String(next.nickname || "").trim(), bio = String(next.bio || "").trim();
    const gender = next.gender ? String(next.gender).trim() : null;
    const birth_year = next.birth_year === "" || next.birth_year == null ? null : Number(next.birth_year);
    const likedGenres = next.likedGenres || [], dislikedGenres = next.dislikedGenres || [];
    if (nickname.length < 2 || nickname.length > 20 || /[\u0000-\u001f]/.test(nickname)) throw new Error("닉네임은 2~20자로 입력해주세요.");
    if (bio.length > 200) throw new Error("소개는 200자까지 적을 수 있어요.");
    if (gender !== null && !["M", "F", "N"].includes(gender)) throw new Error("성별을 확인해주세요.");
    if (birth_year !== null && (!Number.isInteger(birth_year) || birth_year < 1900 || birth_year > 2100)) throw new Error("출생년도는 1900~2100 사이로 입력해주세요.");
    if (likedGenres.some((genre) => dislikedGenres.includes(genre))) throw new Error("같은 장르를 선호·비선호에 동시에 선택할 수 없어요.");
    saving.current = true;
    try {
      const session = await request("/api/auth/me");
      if (session.user.id !== id || owner.current !== id) throw new Error("계정이 변경됐어요. 다시 로그인해주세요.");
      const data = await saveProfile({
        nickname, bio, gender, birth_year, likedGenres, dislikedGenres,
        onboarded: next.onboarded ?? true,
      });
      if (owner.current !== id) throw new Error("계정이 변경됐어요. 다시 로그인해주세요.");
      setProfileState({ owner: id, data }); setProfileError("");
      return true;
    } catch (e) {
      if (owner.current !== id) throw e;
      if (e.status === 401) { invalidate(); throw e; }
      throw e;
    } finally { saving.current = false; }
  }
  return <Context.Provider value={{ user, loading, error, profileLoading: profilesPending, profileError,
    login, logout, updateProfile, invalidate }}>{children}</Context.Provider>;
}
export const useAuth = () => useContext(Context);
