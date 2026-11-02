import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../components/AuthContext';
import { useLibrary } from '../components/LibraryContext';
import { useCommunity } from '../components/CommunityContext';
import GenrePicker from '../components/GenrePicker';
import CommunityPostRow from '../components/CommunityPostRow';
import ReaderProfile from '../components/ReaderProfile';
import PostDetail from '../components/PostDetail';
import { community } from '../communityApi';
export default function ProfilePage() {
  const { user, loading, updateProfile } = useAuth(); const { records } = useLibrary(); const { revision } = useCommunity();
  const [nickname,setNickname]=useState(''),[bio,setBio]=useState(''),[liked,setLiked]=useState([]),[disliked,setDisliked]=useState([]);
  const [message,setMessage]=useState(''),[busy,setBusy]=useState(false),[activity,setActivity]=useState(null),[activityError,setActivityError]=useState(''),[tab,setTab]=useState('posts'),[selected,setSelected]=useState(null),[reader,setReader]=useState(null);
  useEffect(()=>{setNickname(user?.nickname||'');setBio(user?.bio||'');setLiked(user?.likedGenres||[]);setDisliked(user?.dislikedGenres||[]);},[user?.id,user?.onboarded]);
  useEffect(()=>{if(!user)return;let active=true;setActivityError('');community('/me/activity').then(data=>{if(active)setActivity(data);}).catch(e=>{if(active)setActivityError(e.message);});return()=>{active=false;};},[user?.id,revision]);
  async function save(event){event.preventDefault();setBusy(true);setMessage('');try{await updateProfile({nickname:nickname.trim(),bio:bio.trim(),likedGenres:liked,dislikedGenres:disliked,onboarded:true});setMessage('프로필과 취향을 저장했어요.');}catch(e){setMessage(e.message);}finally{setBusy(false);}}
  if(loading)return <main className="container workspace-page"><p role="status">로그인 확인 중…</p></main>;
  if(!user)return <main className="container workspace-page"><h1>내 정보</h1><p>로그인하면 내 정보와 커뮤니티 활동을 볼 수 있어요.</p><Link className="primary-btn" to="/login">로그인하기</Link></main>;
  return <main className="container workspace-page profile-page"><p className="section-kicker">MY READING LIFE</p><h1>내 정보</h1>
    <div className="profile-layout"><section className="profile-preview" aria-label="내 프로필"><div className="profile-avatar">{user.nickname.slice(0,1)}</div><h2>{user.nickname}</h2><p className="profile-bio">{user.bio||'좋아하는 책으로 나를 소개해보세요.'}</p>
      <p>서재 {records.length}권 · 완독 {records.filter(r=>r.status==='COMPLETED').length}권</p><Link className="outline-btn" to="/library">내 서재</Link>
      {activity && <div className="profile-activity-counts"><span>작성 글 <strong>{activity.counts.posts}</strong></span><span>댓글 <strong>{activity.counts.comments}</strong></span><span>한줄평 <strong>{activity.counts.lines}</strong></span></div>}</section>
      <section className="profile-editor"><h2>프로필·취향 수정</h2><form className="editor-form" onSubmit={save}><label>이메일<input type="email" readOnly value={user.email||''}/></label>
        <label>닉네임<input required minLength={2} maxLength={20} value={nickname} onChange={e=>setNickname(e.target.value)}/></label><label>내 소개<textarea aria-label="내 소개" maxLength={200} rows={3} value={bio} onChange={e=>setBio(e.target.value)}/><small>{bio.length}/200</small></label>
        <GenrePicker label="선호하는 장르" value={liked} onChange={setLiked} excluded={disliked}/><GenrePicker label="비선호하는 장르" value={disliked} onChange={setDisliked} excluded={liked}/>
        <button className="primary-btn" disabled={busy}>{busy?'저장 중…':'변경사항 저장'}</button><p role="status">{message}</p><small>닉네임·소개와 공개 글은 다른 독자에게 보여요. 비선호 장르와 개인 서재 기록은 공개하지 않아요.</small></form></section></div>
    <section className="my-community-activity"><h2>내 활동</h2><div className="book-community-tabs">{[['posts','내가 쓴 글'],['comments','내가 쓴 댓글'],['lines','내 한줄평']].map(([value,label])=><button key={value} aria-pressed={tab===value} onClick={()=>setTab(value)}>{label}</button>)}</div>
      {activityError&&<p role="alert">{activityError}</p>}{activity&&(tab==='comments'?(activity.comments.length?activity.comments.map(comment=><button className="activity-comment" key={comment.id} onClick={()=>setSelected(comment.post_id)}><strong>{comment.title}</strong><p>{comment.body}</p><small>{new Date(comment.created_at).toLocaleDateString('ko-KR')}</small></button>):<p>아직 남긴 댓글이 없어요.</p>):(activity.posts.filter(post=>tab!=='lines'||post.kind==='line').length?activity.posts.filter(post=>tab!=='lines'||post.kind==='line').map(post=><CommunityPostRow key={post.id} post={post} onOpen={setSelected} onAuthor={setReader}/>):<p>아직 작성한 글이 없어요.</p>))}
    </section>{selected&&<PostDetail key={selected} postId={selected} close={()=>setSelected(null)}/>}<ReaderProfile profileId={reader} close={()=>setReader(null)}/></main>;
}
