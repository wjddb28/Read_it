import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import PostDetail from '../components/PostDetail';
export default function CommunityPostPage() {
  const { postId } = useParams();
  const location = useLocation(), navigate = useNavigate();
  const requested = location.state?.returnTo;
  const returnTo = typeof requested === 'string' && /^\/(community(?:[?]|$)|profile(?:[?]|$)|search(?:[?]|$)|library(?:[?]|$))/.test(requested) ? requested : '/community';
  return <main className="container workspace-page community-post-page">
    <nav className="board-navigation" aria-label="게시판 이동"><Link to="/community">커뮤니티</Link><span>게시글 읽기</span><Link className="outline-btn" to={returnTo}>목록으로</Link></nav>
    <PostDetail key={postId} postId={postId} close={() => navigate(returnTo, { replace: true })} />
    <div className="board-bottom-actions"><Link className="outline-btn" to={returnTo}>목록으로</Link><Link className="primary-btn" to="/community?write=1">글쓰기</Link></div>
  </main>;
}
