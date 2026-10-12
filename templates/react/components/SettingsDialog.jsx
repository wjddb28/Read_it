import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "./AuthContext";
export default function SettingsDialog({
  open,
  close,
  theme,
  changeTheme,
  message,
}) {
  const { user } = useAuth();
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className="settings-dialog"
      onClose={close}
      aria-labelledby="settingsTitle"
      onClick={(e) => {
        const r = ref.current.getBoundingClientRect();
        if (
          e.target === ref.current &&
          (e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom)
        )
          close();
      }}
    >
      <div className="settings-heading">
        <h2 id="settingsTitle">설정</h2>
        <button
          className="settings-close"
          aria-label="설정 닫기"
          onClick={close}
        >
          ×
        </button>
      </div>
      <section>
        <h3>화면 모드</h3>
        <p>편한 화면으로 책을 둘러보세요.</p>
        <fieldset className="theme-options">
          <legend className="sr-only">화면 모드 선택</legend>
          {["light", "dark"].map((value) => (
            <label
              key={value}
              className={"theme-choice " + (theme === value ? "selected" : "")}
            >
              <input
                type="radio"
                name="theme"
                value={value}
                checked={theme === value}
                onChange={() => changeTheme(value)}
              />
              <span
                className={"theme-preview preview-" + value}
                aria-hidden="true"
              />
              <strong>{value === "light" ? "라이트 모드" : "다크 모드"}</strong>
            </label>
          ))}
        </fieldset>
        <p role="status" className="settings-note">
          {message}
        </p>
      </section>
      <section className="account-settings">
        <h3>내 정보</h3>
        <p>
          {user
            ? `${user.nickname}${user.email ? ` · ${user.email}` : ""}`
            : "로그인하면 내 서재와 독서 기록을 저장할 수 있어요."}
        </p>
        <Link
          className="primary-btn"
          to={user ? "/library" : "/login"}
          onClick={close}
        >
          {user ? "내 서재" : "로그인"}
        </Link>
      </section>
    </dialog>
  );
}
