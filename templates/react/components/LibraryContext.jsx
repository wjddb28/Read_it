import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthContext";
import { request } from "../api";
const Context = createContext(null);
export function LibraryProvider({ children }) {
  const { user, invalidate } = useAuth();
  const [state, setState] = useState({ owner: null, records: [] });
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const lock = useRef(false);
  const owner = useRef(user?.id);
  owner.current = user?.id;
  const records = state.owner === user?.id ? state.records : [];
  useEffect(() => {
    let active = true;
    setNotice("");
    if (!user) {
      setState({ owner: null, records: [] });
      setLoading(false);
      return () => {
        active = false;
      };
    }
    const userId = user.id;
    setState({ owner: userId, records: [] });
    setLoading(true);
    request("/api/library")
      .then((data) => {
        if (active && owner.current === userId)
          setState({ owner: userId, records: data.records });
      })
      .catch((e) => {
        if (!active) return;
        if (e.status === 401) invalidate();
        setNotice(
          e.status === 401
            ? "로그인이 만료됐어요. 다시 로그인해주세요."
            : "서재를 불러오지 못했어요. 서버 연결을 확인해주세요.",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [user?.id]);
  async function save(url, method, body) {
    if (!user) {
      setNotice("로그인 후 내 서재에 저장할 수 있어요.");
      return false;
    }
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    const userId = user.id;
    try {
      if (owner.current !== userId) return false;
      const data = await request(url, {
        method,
        ...(body
          ? {
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            }
          : {}),
      });
      if (owner.current !== userId) return false;
      setNotice("서재를 저장했어요.");
      return data;
    } catch (e) {
      if (e.status === 401) invalidate();
      setNotice(
        e.status === 401
          ? "로그인이 만료됐어요. 다시 로그인해주세요."
          : e.status === 409
            ? "이미 서재에 담긴 책이에요."
            : "저장하지 못했어요. 서버 연결을 확인해주세요.",
      );
      return null;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function add(book) {
    const id = String(book.isbn || `${book.title}|${book.author}`);
    if (records.some((item) => item.id === id)) {
      setNotice("이미 서재에 담긴 책이에요.");
      return false;
    }
    if (!book.isbn) {
      setNotice("ISBN이 있는 책만 서재에 담을 수 있어요.");
      return false;
    }
    return save("/api/library", "POST", { isbn: book.isbn }).then((data) => {
      if (!data) return false;
      setState((current) =>
        current.owner === user?.id
          ? { ...current, records: [...current.records, data.record] }
          : current,
      );
      return true;
    });
  }
  function update(id, patch) {
    const current = records.find((item) => item.id === id);
    if (!current) return Promise.resolve(false);
    const next = { ...current, ...patch };
    return save(`/api/library/${encodeURIComponent(id)}`, "PUT", {
      status: next.status,
      startDate: next.startDate || null,
      endDate: next.endDate || null,
      rating: next.rating || 0,
      review: next.review || "",
      logs: next.logs || {},
    }).then((data) => {
      if (!data) return false;
      setState((state) =>
        state.owner === user?.id
          ? {
              ...state,
              records: state.records.map((item) =>
                item.id === id ? data.record : item,
              ),
            }
          : state,
      );
      return true;
    });
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
    return save(`/api/library/${encodeURIComponent(id)}`, "DELETE").then(
      (data) => {
        if (!data) return false;
        setState((current) =>
          current.owner === user?.id
            ? {
                ...current,
                records: current.records.filter((item) => item.id !== id),
              }
            : current,
        );
        return true;
      },
    );
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
