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
      const timeout = window.setTimeout(() => {
        googleScript = null;
        script.remove();
        reject(new Error("구글 로그인 연결이 지연되고 있어요. 다시 시도해주세요."));
      }, 15000);
      script.onload = () => { window.clearTimeout(timeout); resolve(); };
      script.onerror = () => {
        window.clearTimeout(timeout);
        script.remove();
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
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);
  useEffect(() => {
    let active = true;
    setMessage("");
    setLoading(true);
    if (button.current) button.current.replaceChildren();
    request("/api/auth/config").then(async (config) => {
      if (!config.client_id) throw new Error("구글 로그인을 준비하지 못했어요. 잠시 후 다시 시도해주세요.");
      await loadGoogle();
      return [config];
    })
      .then(([config]) => {
        if (!active || !button.current) return;
        if (!config.client_id)
          throw new Error("구글 로그인을 준비하지 못했어요. 잠시 후 다시 시도해주세요.");
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
      }).finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [signup, retry]);
  return (
    <main className="auth-page">
      <section className="auth-box" aria-label={signup ? "회원가입" : "로그인"} aria-busy={loading || busy}>
        <p className="section-kicker">READ-IT</p>
        <h1>{signup ? "회원가입" : "로그인"}</h1>
        {loading && <p role="status">구글 로그인 버튼을 준비하고 있어요…</p>}
        <div className="google-button" ref={button} inert={busy ? true : undefined} />
        <p className="auth-caption">
          {signup
            ? "구글 계정으로 시작해보세요."
            : "구글 계정으로 내 서재를 열어보세요."}
        </p>
        {busy && <p role="status">로그인 중…</p>}
        <p role="alert" className="auth-message">
          {message}
        </p>
        {message && <button type="button" className="outline-btn" disabled={loading || busy}
          onClick={() => setRetry((n) => n + 1)}>다시 시도</button>}
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
