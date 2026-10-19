import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../components/AuthContext";
import { useLibrary } from "../components/LibraryContext";
export default function ProfilePage() {
  const { user, loading, updateProfile } = useAuth();
  const { records } = useLibrary();
  const [nickname, setNickname] = useState("");
  const [bio, setBio] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setNickname(user?.nickname || ""); setBio(user?.bio || ""); setMessage("");
  }, [user?.id]);
  async function save(event) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      await updateProfile({ nickname, bio });
      setNickname(nickname.trim()); setBio(bio.trim());
      setMessage("닉네임과 소개를 저장했어요.");
    } catch (error) { setMessage(error.message || "저장하지 못했어요. 브라우저 저장 공간을 확인해주세요."); }
    finally { setBusy(false); }
  }
  if (loading) return <main className="container workspace-page"><p role="status">로그인 확인 중…</p></main>;
  if (!user) return <main className="container workspace-page"><h1>내 정보</h1>
    <p>로그인하면 닉네임과 소개를 수정할 수 있어요.</p><Link className="primary-btn" to="/login">로그인하기</Link></main>;
  return <main className="container workspace-page profile-page">
    <p className="section-kicker">MY PROFILE</p><h1>내 정보</h1>
    <p className="page-subtitle">책으로 나를 소개해보세요.</p>
    <div className="profile-layout">
      <section className="profile-preview" aria-label="내 프로필 미리보기">
        <div className="profile-avatar" aria-hidden="true">{(user.nickname || "독자").slice(0, 1)}</div>
        <h2>{user.nickname}</h2>
        <p className="profile-bio">{user.bio || "아직 소개가 없어요. 좋아하는 책이나 장르를 적어보세요."}</p>
        <p>서재 {records.length}권 · 완독 {records.filter((record) => record.status === "COMPLETED").length}권</p>
        <Link className="outline-btn" to="/library">내 서재 보기</Link>
      </section>
      <section className="profile-editor"><h2>프로필 수정</h2>
        <form className="editor-form" onSubmit={save}>
          <label>이메일<input type="email" value={user.email || ""} readOnly /></label>
          <label>닉네임<input value={nickname} onChange={(event) => setNickname(event.target.value)}
            required minLength={2} maxLength={20} autoComplete="nickname" /></label>
          <label>내 소개<textarea aria-label="내 소개" rows={5} maxLength={200} value={bio} onChange={(event) => setBio(event.target.value)}
            placeholder="좋아하는 장르, 기억에 남은 책, 나의 독서 취향을 소개해주세요." />
            <small>{bio.length} / 200</small></label>
          <button className="primary-btn" disabled={busy}>{busy ? "저장 중…" : "변경사항 저장"}</button>
          <p role="status">{message}</p>
          <small>닉네임과 소개는 로그인한 계정별로 이 브라우저에 저장돼요. 아직 다른 사용자에게 공개되지는 않아요.</small>
        </form>
      </section>
    </div>
  </main>;
}
