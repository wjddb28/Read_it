import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { request } from "../api";
import { useAuth } from "../components/AuthContext";
let googleScript;
function loadGoogle() {
  if (window.google?.accounts) return Promise.resolve();
  if (!googleScript)
    googleScript = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.onload = resolve;
      script.onerror = () => {
        googleScript = null;
        reject(new Error("구글 로그인 버튼을 불러오지 못했어요."));
      };
      document.head.appendChild(script);
    });
  return googleScript;
}
export default function AuthPage({ signup = false }) {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const button = useRef(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);
  useEffect(() => {
    let active = true;
    setMessage("");
    Promise.all([request("/api/auth/config"), loadGoogle()])
      .then(([config]) => {
        if (!active || !button.current) return;
        if (!config.client_id)
          throw new Error("서버의 구글 클라이언트 ID를 설정해주세요.");
        window.google.accounts.id.initialize({
          client_id: config.client_id,
          callback: async ({ credential }) => {
            if (!active) return;
            setBusy(true);
            try {
              await login("google", { credential });
              navigate("/");
            } catch (e) {
              if (active) setMessage(e.message);
            } finally {
              if (active) setBusy(false);
            }
          },
        });
        window.google.accounts.id.renderButton(button.current, {
          theme: "outline",
          size: "large",
          text: signup ? "signup_with" : "signin_with",
          width: 280,
          locale: "ko",
        });
      })
      .catch((e) => {
        if (active) setMessage(e.message);
      });
    return () => {
      active = false;
    };
  }, [signup]);
  return (
    <main className="auth-page">
      <section className="auth-box">
        <p className="section-kicker">READ-IT</p>
        <h1>{signup ? "회원가입" : "로그인"}</h1>
        <p className="page-subtitle">나의 독서 기록을 한곳에.</p>
        <div className="google-button" ref={button} />
        <p className="auth-caption">
          {signup
            ? "구글 계정으로 시작해보세요."
            : "구글 계정으로 내 서재를 열어보세요."}
        </p>
        {busy && <p role="status">로그인 중…</p>}
        <p role="status" className="auth-message">
          {message}
        </p>
        <p className="switch">
          {signup ? "이미 계정이 있나요?" : "계정이 없나요?"}{" "}
          <Link to={signup ? "/login" : "/signup"}>
            {signup ? "로그인" : "회원가입"}
          </Link>
        </p>
      </section>
    </main>
  );
}
