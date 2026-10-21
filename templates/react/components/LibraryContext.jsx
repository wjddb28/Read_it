import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthContext";
import { request } from "../api";
const Context = createContext(null);
const PREFIX = "readit.library.google.v1:";
function load(userId) {
  if (!userId) return [];
  try {
    const data = JSON.parse(localStorage.getItem(PREFIX + userId) || "[]");
    return Array.isArray(data)
      ? data.filter(
          (item) =>
            item?.id &&
            item.book &&
            ["WISH", "READING", "COMPLETED"].includes(item.status),
        )
      : [];
  } catch {
    return [];
  }
}
export function LibraryProvider({ children }) {
  const { user, invalidate } = useAuth();
  const [state, setState] = useState({ owner: null, records: [] });
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const owner = useRef(user?.id);
  owner.current = user?.id;
  const records = state.owner === user?.id ? state.records : [];
  useEffect(() => {
    setState({ owner: user?.id, records: load(user?.id) });
    setNotice("");
    const sync = (event) => {
      if (event.key === PREFIX + user?.id || event.key === null)
        setState({ owner: user?.id, records: load(user?.id) });
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, [user?.id]);
  async function save(transform) {
    if (!user) {
      setNotice("로그인 후 내 서재에 저장할 수 있어요.");
      return false;
    }
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    const userId = user.id;
    try {
      // 저장 직전에도 서버에서 로그인 유효성을 확인합니다. DB 호출은 없습니다.
      const session = await request("/api/auth/me");
      if (owner.current !== userId || session.user.id !== userId) return false;
      const previous = load(userId),
        next = transform(previous);
      if (!next) return false;
      localStorage.setItem(PREFIX + userId, JSON.stringify(next));
      setState({ owner: userId, records: next });
      setNotice("로그인한 계정의 기록을 이 브라우저에 저장했어요.");
      return true;
    } catch (e) {
      if (e.status === 401) invalidate();
      setNotice(
        e.status === 401
          ? "로그인이 만료됐어요. 다시 로그인해주세요."
          : "저장하지 못했어요. 서버 연결과 브라우저 저장 공간을 확인해주세요.",
      );
      return false;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function add(book) {
    const id = String(book.isbn || `${book.title}|${book.author}`);
    return save((previous) => {
      if (previous.some((x) => x.id === id)) {
        setNotice("이미 서재에 담긴 책이에요.");
        return null;
      }
      return [
        ...previous,
        {
          id,
          book,
          status: "WISH",
          startDate: "",
          endDate: "",
          rating: 0,
          review: "",
          logs: {},
        },
      ];
    });
  }
  function update(id, patch) {
    return save((previous) =>
      previous.map((x) => (x.id === id ? { ...x, ...patch } : x)),
    );
  }
  function updateLog(id, day, memo) {
    return save((previous) => {
      if (!previous.some((record) => record.id === id)) {
        setNotice("서재에서 책을 찾지 못했어요."); return null;
      }
      return previous.map((record) => {
        if (record.id !== id) return record;
        const logs = { ...record.logs };
        if (memo === null) delete logs[day];
        else logs[day] = memo;
        return { ...record, logs };
      });
    });
  }
  function remove(id) {
    return save((previous) => previous.filter((x) => x.id !== id));
  }
  return (
    <Context.Provider
      value={{ records, add, update, updateLog, remove, notice, busy, loading: false }}
    >
      {children}
    </Context.Provider>
  );
}
export const useLibrary = () => useContext(Context);
