import { useEffect, useState } from "react";
import "../../static/css/react/ui-fixes.css";
import { Link, NavLink, Routes, Route } from "react-router-dom";
import { AuthProvider, useAuth } from "./components/AuthContext";
import SearchPage from "./pages/SearchPage";
import CommunityPage from "./pages/CommunityPage";
import LibraryPage from "./pages/LibraryPage";
import { LibraryProvider } from "./components/LibraryContext";
import AuthPage from "./pages/AuthPage";
import ProfilePage from "./pages/ProfilePage";
import SettingsDialog from "./components/SettingsDialog";
export default function App() {
  return (
    <AuthProvider>
      <Application />
    </AuthProvider>
  );
}
function Application() {
  const { user, logout } = useAuth();
  const [accountError, setAccountError] = useState("");
  const [settings, setSettings] = useState(false);
  const [theme, setTheme] = useState(
    () => document.documentElement.dataset.theme || "light",
  );
  const [themeMessage, setThemeMessage] = useState("");
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    const sync = (e) => {
      if (e.key === "readit.theme" || e.key === null)
        setTheme(e.newValue === "dark" ? "dark" : "light");
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  function changeTheme(value) {
    setTheme(value);
    try {
      localStorage.setItem("readit.theme", value);
      setThemeMessage("화면 모드를 저장했어요.");
    } catch {
      setThemeMessage(
        "현재 화면에 적용했어요. 이 브라우저에서는 저장할 수 없어요.",
      );
    }
  }
  return (
    <LibraryProvider>
      <header className="header">
        <div className="container nav">
          <Link to="/" className="logo">
            Read-it
          </Link>
          <nav className="nav-menu">
            <NavLink to="/" end>
              홈
            </NavLink>
            <NavLink to="/search">도서 검색</NavLink>
            <NavLink to="/community">커뮤니티</NavLink>
            <NavLink to="/library">내 서재</NavLink>
          </nav>
          <div className="nav-actions">
            {user ? (
              <>
                <span className="account-name">{user.nickname}</span>
                <button
                  className="header-logout"
                  onClick={async () => {
                    try {
                      await logout();
                    } catch (e) {
                      setAccountError(e.message);
                    }
                  }}
                >
                  로그아웃
                </button>
              </>
            ) : (
              <>
                <Link to="/login" className="login-link">
                  로그인
                </Link>
                <Link to="/signup" className="signup-btn">
                  회원가입
                </Link>
              </>
            )}
            <button
              className="settings-open"
              onClick={() => {
                setThemeMessage("");
                setSettings(true);
              }}
              aria-haspopup="dialog"
            >
              설정
            </button>
            {accountError && <span role="alert">{accountError}</span>}
          </div>
        </div>
      </header>
      <HashScroll />
      <Routes>
        <Route path="/" element={<LibraryPage />} />
        <Route path="/login" element={<AuthPage />} />
        <Route path="/login.html" element={<AuthPage />} />
        <Route path="/signup" element={<AuthPage signup />} />
        <Route path="/signup.html" element={<AuthPage signup />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/community" element={<CommunityPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route
          path="*"
          element={
            <main className="container pending-page">
              <h1>페이지를 찾을 수 없어요</h1>
              <Link to="/">홈으로</Link>
            </main>
          }
        />
      </Routes>
      <footer className="footer">
        <div className="container footer-inner">
          <div>
            <strong className="footer-logo">Read-it</strong>
            <p>도서 기록과 추천을 위한 독서 커뮤니티</p>
          </div>
          <p className="copyright">© 2026 Read-it Graduation Project</p>
        </div>
      </footer>
      <SettingsDialog
        open={settings}
        close={() => setSettings(false)}
        theme={theme}
        changeTheme={changeTheme}
        message={themeMessage}
      />
    </LibraryProvider>
  );
}
import { useLocation } from "react-router-dom";
function HashScroll() {
  const location = useLocation();
  useEffect(() => {
    if (location.hash) {
      const timer = setTimeout(
        () =>
          document
            .getElementById(location.hash.slice(1))
            ?.scrollIntoView({ behavior: "smooth" }),
        0,
      );
      return () => clearTimeout(timer);
    }
    window.scrollTo(0, 0);
  }, [location.pathname, location.hash]);
  return null;
}
