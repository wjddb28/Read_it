import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../components/AuthContext";
export default function ProfilePage() {
  const { user, loading, profileLoading, profileError, updateProfile } = useAuth();
  const [nickname, setNickname] = useState("");
  const [bio, setBio,] = useState("");
  const [gender, setGender] = useState("");
  const [birth_year, setBirthYear] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setNickname(user?.nickname || "");
    setBio(user?.bio || "");
    setGender(user?.gender || "");
    setBirthYear(user?.birth_year || "");
  }, [user?.id, user?.nickname, user?.bio, user?.gender, user?.birth_year, profileLoading]);
  useEffect(() => setMessage(""), [user?.id]);
  async function save(event) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      await updateProfile({ nickname, bio, gender, birth_year });
      setNickname(nickname.trim()); setBio(bio.trim());
      setGender(gender.trim());
      setBirthYear(birth_year);
      setMessage("닉네임과 소개를 저장했어요.");
    } catch (error) { setMessage(error.message || "프로필을 저장하지 못했어요. 서버 연결을 확인해주세요."); }
    finally { setBusy(false); }
  }
  if (loading || (user && profileLoading))
    return <main className="container workspace-page"><p role="status">프로필을 불러오는 중…</p></main>;
  if (!user) return <main className="container workspace-page"><h1>내 정보</h1>
    <p>로그인하면 닉네임과 소개를 수정할 수 있어요.</p><Link className="primary-btn" to="/login">로그인하기</Link></main>;
  const stats = user.stats;
  return <main className="container workspace-page profile-page">
    <p className="section-kicker">MY PROFILE</p><h1>내 정보</h1>
    <p className="page-subtitle">책으로 나를 소개해보세요.</p>
    {profileError && <p role="alert">{profileError}</p>}
    <div className="profile-layout">
      <section className="profile-preview" aria-label="내 프로필 미리보기">
        <div className="profile-avatar" aria-hidden="true">{(user.nickname || "독자").slice(0, 1)}</div>
        <h2>{user.nickname}</h2>
        <p className="profile-bio">{user.bio || "아직 소개가 없어요. 좋아하는 책이나 장르를 적어보세요."}</p>
        {stats ? <>
          <p>서재 {stats.total_books}권 · 완독 {stats.completed_books}권</p>
          <p>총 독서 시간 {stats.total_reading_minutes}분</p>
        </> : <p role="status">서재 통계를 불러올 수 없어요.</p>}
        <Link className="outline-btn" to="/library">내 서재 보기</Link>
      </section>
      <section className="profile-editor"><h2>프로필 수정</h2>
        <form className="editor-form" onSubmit={save}>
          <label>이메일<input type="email" value={user.email || ""} readOnly /></label>
          <label>닉네임<input value={nickname} onChange={(event) => setNickname(event.target.value)}
            required minLength={2} maxLength={20} autoComplete="nickname" /></label>
          <label>성별<select value={gender} onChange={(event) => setGender(event.target.value)}
            required><option value="">선택</option><option value="M">남성</option><option value="F">여성</option><option value="N">응답 거부</option></select></label>
          <label>출생년도<input type="number" value={birth_year} onChange={(event) => setBirthYear(event.target.value)}
             min={1900} max={2100} /></label>
          <label>내 소개<textarea aria-label="내 소개" rows={5} maxLength={200} value={bio} onChange={(event) => setBio(event.target.value)}
            placeholder="좋아하는 장르, 기억에 남은 책, 나의 독서 취향을 소개해주세요." />
            <small>{bio.length} / 200</small></label>
          <button className="primary-btn" disabled={busy}>{busy ? "저장 중…" : "변경사항 저장"}</button>
          <p role="status">{message}</p>
        </form>
      </section>
    </div>
  </main>;
}
