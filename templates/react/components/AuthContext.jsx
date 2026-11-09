import { createContext, useContext, useEffect, useRef, useState } from "react";
import { getProfile, request, saveProfile } from "../api";
import { community, sendCommunity } from "../communityApi";

const Context = createContext(null);
function legacy(id) {
  try { return JSON.parse(localStorage.getItem("readit.profile.v1:" + id) || "{}"); }
  catch { return {}; }
}

export function AuthProvider({ children }) {
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [profileState, setProfileState] = useState({ owner: null, data: null, community: null });
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState("");
  const owner = useRef(null), saving = useRef(false);
  owner.current = account?.id;
  const state = profileState.owner === account?.id ? profileState : null;
  const profile = state?.data, publicProfile = state?.community;
  const profilesPending = !!account && (profileState.owner !== account.id || profileLoading);
  const saved = account ? legacy(account.id) : {};
  // MySQL owns basic profile fields; the community owns tastes and onboarding.
  const user = account ? {
    ...account, ...(publicProfile || {}),
    nickname: profile?.nickname ?? (publicProfile?.onboarded ? publicProfile.nickname : saved.nickname || account.nickname),
    bio: profile ? profile.about_me || "" : publicProfile?.onboarded ? publicProfile.bio || "" : saved.bio || "",
    stats: profile?.stats, gender: profile?.gender ?? null, birth_year: profile?.birth_year ?? null,
    communityReady: !!publicProfile,
  } : null;

  function invalidate() {
    owner.current = null;
    setAccount(null);
    setProfileState({ owner: null, data: null, community: null });
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
    setProfileState({ owner: id || null, data: null, community: null });
    setProfileError("");
    if (!id) {
      setProfileLoading(false);
      return () => { active = false; };
    }
    setProfileLoading(true);
    Promise.allSettled([getProfile(), community("/me")]).then(([basic, social]) => {
      if (!active || owner.current !== id) return;
      const failures = [basic, social].filter((result) => result.status === "rejected");
      if (failures.some((result) => result.reason.status === 401)) { invalidate(); return; }
      setProfileState({ owner: id,
        data: basic.status === "fulfilled" ? basic.value : null,
        community: social.status === "fulfilled" ? social.value.profile : null });
      setProfileError(failures.map((result) => result.reason.message).join(" "));
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
    let basicSaved = false;
    try {
      const session = await request("/api/auth/me");
      if (session.user.id !== id || owner.current !== id) throw new Error("계정이 변경됐어요. 다시 로그인해주세요.");
      const data = await saveProfile({ nickname, bio, gender, birth_year });
      if (owner.current !== id) throw new Error("계정이 변경됐어요. 다시 로그인해주세요.");
      basicSaved = true;
      setProfileState((current) => current.owner === id ? { ...current, data } : current);
      const { profile: social } = await sendCommunity("/me", {
        nickname, bio, likedGenres, dislikedGenres, onboarded: next.onboarded ?? true,
      }, "PUT");
      if (owner.current !== id) throw new Error("계정이 변경됐어요. 다시 로그인해주세요.");
      setProfileState({ owner: id, data, community: social }); setProfileError("");
      return true;
    } catch (e) {
      if (owner.current !== id) throw e;
      if (e.status === 401) { invalidate(); throw e; }
      if (basicSaved) {
        const message = "기본 프로필은 저장됐지만 커뮤니티 프로필·취향은 저장하지 못했어요. " + e.message + " 다시 저장해주세요.";
        setProfileError(message); throw new Error(message);
      }
      throw e;
    } finally { saving.current = false; }
  }
  return <Context.Provider value={{ user, loading, error, profileLoading: profilesPending, profileError,
    login, logout, updateProfile, invalidate }}>{children}</Context.Provider>;
}
export const useAuth = () => useContext(Context);
