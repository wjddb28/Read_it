import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../components/AuthContext";
import { useLibrary } from "../components/LibraryContext";
import { useCommunity } from "../components/CommunityContext";
import GenrePicker from "../components/GenrePicker";
import CommunityPostRow from "../components/CommunityPostRow";
import OneLineReviewList from "../components/OneLineReviewList";
import ReaderProfile from "../components/ReaderProfile";
import ProfileAvatar from "../components/ProfileAvatar";
import { community, sendCommunity } from "../communityApi";

export default function ProfilePage() {
  const navigate = useNavigate();
  const { user, loading, profileLoading, profileError, updateProfile } = useAuth();
  const { records } = useLibrary();
  const { revision } = useCommunity();
  const [nickname, setNickname] = useState(""), [bio, setBio] = useState("");
  const [gender, setGender] = useState(""), [birthYear, setBirthYear] = useState("");
  const [liked, setLiked] = useState([]), [disliked, setDisliked] = useState([]);
  const [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const [photoMessage, setPhotoMessage] = useState(""), [photoBusy, setPhotoBusy] = useState(false);
  const [photoVersion, setPhotoVersion] = useState(0);
  const [activity, setActivity] = useState(null), [activityError, setActivityError] = useState("");
  const [tab, setTab] = useState("posts"), [reader, setReader] = useState(null);
  const tasteSignature = JSON.stringify([user?.likedGenres, user?.dislikedGenres]);
  useEffect(() => {
    if (busy) return;
    setNickname(user?.nickname || ""); setBio(user?.bio || "");
    setGender(user?.gender || ""); setBirthYear(user?.birth_year || "");
    setLiked(user?.likedGenres || []); setDisliked(user?.dislikedGenres || []);
  }, [user?.id, user?.nickname, user?.bio, user?.gender, user?.birth_year, tasteSignature]);
  useEffect(() => { setMessage(""); setReader(null); }, [user?.id]);
  useEffect(() => {
    let active = true; setActivity(null); setActivityError("");
    if (!user?.communityReady) return () => { active = false; };
    community("/me/activity").then((data) => { if (active) setActivity(data); })
      .catch((e) => { if (active) setActivityError(e.message); });
    return () => { active = false; };
  }, [user?.id, user?.communityReady, revision]);
  async function save(event) {
    event.preventDefault(); setBusy(true); setMessage("");
    try {
      await updateProfile({ nickname, bio, gender, birth_year: birthYear,
        likedGenres: liked, dislikedGenres: disliked, onboarded: true });
      setNickname(nickname.trim()); setBio(bio.trim());
      setMessage("프로필과 취향을 저장했어요.");
    } catch (e) { setMessage(e.message); }
    finally { setBusy(false); }
  }
  async function changePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 3 * 1024 * 1024) {
      setPhotoMessage("3MB 이하의 JPG·PNG·WebP 사진을 선택해주세요.");
      return;
    }
    setPhotoBusy(true); setPhotoMessage("");
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => typeof reader.result === "string"
          ? resolve(reader.result)
          : reject(new Error("사진 파일을 읽지 못했어요."));
        reader.onerror = () => reject(new Error("사진 파일을 읽지 못했어요."));
        reader.readAsDataURL(file);
      });
      await sendCommunity("/pfp", { data });
      setPhotoVersion(Date.now());
      setPhotoMessage("프로필 사진을 변경했어요.");
    } catch (e) { setPhotoMessage(e.message); }
    finally { setPhotoBusy(false); }
  }
  async function deletePhoto() {
    setPhotoBusy(true); setPhotoMessage("");
    try {
      await sendCommunity("/pfp", {}, "DELETE");
      setPhotoVersion(Date.now());
      setPhotoMessage("프로필 사진을 삭제했어요.");
    } catch (e) { setPhotoMessage(e.message); }
    finally { setPhotoBusy(false); }
  }
  if (loading || (user && profileLoading))
    return <main className="container workspace-page"><p role="status">프로필을 불러오는 중…</p></main>;
  if (!user) return <main className="container workspace-page"><h1>내 정보</h1>
    <Link className="primary-btn" to="/login">로그인하기</Link></main>;
  const stats = user.stats;
  const posts = activity?.posts.filter((post) =>
    tab === "lines" ? post.kind === "line" : post.kind !== "line") || [];
  return <main className="container workspace-page profile-page">
    <h1>내 정보</h1>
    {profileError && <p role="alert">{profileError}</p>}
    <div className="profile-layout">
      <section className="profile-preview" aria-label="내 프로필">
        <ProfileAvatar profileId={user.profileId} name={user.nickname} refreshKey={photoVersion} />

        <h2>{user.nickname}</h2>{user.bio && <p className="profile-bio">{user.bio}</p>}
        <p>서재 {stats?.total_books ?? records.length}권 · 완독 {stats?.completed_books ?? records.filter((r) => r.status === "COMPLETED").length}권</p>
        {stats && <p>총 독서 시간 {stats.total_reading_minutes}분</p>}
        <Link className="outline-btn" to="/library">내 서재</Link>
        {activity && <div className="profile-activity-counts"><span>작성 글 <strong>{activity.counts.posts}</strong></span>
          <span>댓글 <strong>{activity.counts.comments}</strong></span><span>한줄평 <strong>{activity.counts.lines}</strong></span></div>}
              <div className="profile-photo-actions">
          <label className="outline-btn">사진 올리기
            <input type="file" accept="image/jpeg,image/png,image/webp" disabled={photoBusy}
              onChange={changePhoto} aria-label="프로필 사진 업로드" />
          </label>
          <button type="button" className="text-btn" disabled={photoBusy} onClick={deletePhoto}>
            {photoBusy ? "처리 중…" : "사진 삭제"}
          </button>
        </div>
        <p role="status" aria-live="polite">{photoMessage}</p>
      </section>
      <section className="profile-editor"><h2>프로필·취향 수정</h2>
        <form className="editor-form" onSubmit={save}>
          <label>이메일<input type="email" readOnly value={user.email || ""} /></label>
          <label>닉네임<input required minLength={2} maxLength={20} value={nickname} autoComplete="nickname" onChange={(e) => setNickname(e.target.value)} /></label>
          <label>성별<select value={gender} onChange={(e) => setGender(e.target.value)}>
            <option value="">미선택</option><option value="M">남성</option><option value="F">여성</option><option value="N">응답 거부</option>
          </select></label>
          <label>출생년도<input type="number" min={1900} max={2100} value={birthYear} onChange={(e) => setBirthYear(e.target.value)} /></label>
          <label>내 소개<textarea aria-label="내 소개" maxLength={200} rows={3} value={bio} onChange={(e) => setBio(e.target.value)} /><small>{bio.length}/200</small></label>
          <GenrePicker label="선호하는 장르" value={liked} onChange={setLiked} excluded={disliked} />
          <GenrePicker label="비선호하는 장르" value={disliked} onChange={setDisliked} excluded={liked} />
          <button className="primary-btn" disabled={busy}>{busy ? "저장 중…" : "변경사항 저장"}</button>
          <p role="status">{message}</p>
        </form>
      </section>
    </div>
    <section className="my-community-activity"><h2>내 활동</h2>
      <div className="book-community-tabs">{[["posts", "내가 쓴 글"], ["comments", "내가 쓴 댓글"], ["lines", "내 한줄평"]].map(([value, label]) =>
        <button key={value} aria-pressed={tab === value} onClick={() => setTab(value)}>{label}</button>)}</div>
      {activityError && <p role="alert">{activityError}</p>}
      {activity && (tab === "lines" ? (activity.lines?.length ? <OneLineReviewList lines={activity.lines} showBook /> : <p>아직 남긴 한줄평이 없어요.</p>) : tab === "comments" ? (activity.comments.length ? activity.comments.map((comment) =>
        <button className="activity-comment" key={comment.id} onClick={() => navigate('/community/posts/' + encodeURIComponent(comment.post_id), { state: { returnTo: '/profile' } })}>
          <strong>{comment.title}</strong><p>{comment.body}</p><small>{new Date(comment.created_at).toLocaleDateString("ko-KR")}</small>
        </button>) : <p>아직 남긴 댓글이 없어요.</p>) : (posts.length ? posts.map((post) =>
        <CommunityPostRow key={post.id} post={post} onAuthor={setReader} />) : <p>아직 작성한 글이 없어요.</p>))}
    </section>
    <ReaderProfile profileId={reader} close={() => setReader(null)} />
  </main>;
}
