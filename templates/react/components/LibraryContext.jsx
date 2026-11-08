import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthContext";
import { request } from "../api";
const Context = createContext(null);

async function loadDailyLogs(record) {
  const data = await request(
    `/api/library/${encodeURIComponent(record.id)}/logs`,
  );
  const entries = Object.entries(data.logs);
  return {
    ...record,
    logs: Object.fromEntries(
      entries.map(([day, log]) => [day, log.content]),
    ),
    readingMinutes: Object.fromEntries(
      entries.map(([day, log]) => [day, log.readingMinutes]),
    ),
  };
}

async function loadBookReview(record) {
  const review = await request(
    `/api/library/${encodeURIComponent(record.id)}/review`,
  );
  return withBookReview(record, review);
}

function withBookReview(record, review) {
  return {
    ...record,
    rating: review.rating,
    content: review.content,
    review: review.content,
    hasSpoiler: review.has_spoiler,
  };
}

function withDailyLog(record, day, log) {
  const logs = { ...record.logs };
  const readingMinutes = { ...record.readingMinutes };
  if (log) {
    logs[day] = log.content;
    readingMinutes[day] = log.readingMinutes;
  } else {
    delete logs[day];
    delete readingMinutes[day];
  }
  return { ...record, logs, readingMinutes };
}

export function LibraryProvider({ children }) {
  const { user, invalidate } = useAuth();
  const [state, setState] = useState({ owner: null, records: [] });
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const lock = useRef(false);
  const logRequestCount = useRef(0);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const reviewRequestCount = useRef(0);
  const [loadingReviews, setLoadingReviews] = useState(false);
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
      .then((data) =>
        Promise.all(
          data.records.map(async (record) => {
            const [withLogs, withReview] = await Promise.all([
              loadDailyLogs(record),
              loadBookReview(record),
            ]);
            return {
              ...withReview,
              logs: withLogs.logs,
              readingMinutes: withLogs.readingMinutes,
            };
          }),
        ),
      )
      .then((records) => {
        if (active && owner.current === userId)
          setState({ owner: userId, records });
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
  async function loadDailyLog(id, day) {
    if (!user || !records.some((record) => record.id === id)) return false;
    const userId = user.id;
    logRequestCount.current += 1;
    setLoadingLogs(true);
    try {
      const params = new URLSearchParams({ date: day });
      const data = await request(
        `/api/library/${encodeURIComponent(id)}/logs?${params}`,
      );
      if (owner.current !== userId) return false;
      setState((current) =>
        current.owner === userId
          ? {
              ...current,
              records: current.records.map((record) =>
                record.id === id
                  ? withDailyLog(record, day, data.log)
                  : record,
              ),
            }
          : current,
      );
      return true;
    } catch (e) {
      if (e.status === 401) invalidate();
      setNotice(
        e.status === 401
          ? "로그인이 만료됐어요. 다시 로그인해주세요."
          : "독서 기록을 불러오지 못했어요. 서버 연결을 확인해주세요.",
      );
      return false;
    } finally {
      logRequestCount.current -= 1;
      setLoadingLogs(logRequestCount.current > 0);
    }
  }
  async function loadBookReviewForRecord(id) {
    const record = records.find((item) => item.id === id);
    if (!user || !record) return false;
    const userId = user.id;
    reviewRequestCount.current += 1;
    setLoadingReviews(true);
    try {
      const review = await request(
        `/api/library/${encodeURIComponent(id)}/review`,
      );
      if (owner.current !== userId) return false;
      setState((current) =>
        current.owner === userId
          ? {
              ...current,
              records: current.records.map((item) =>
                item.id === id ? withBookReview(item, review) : item,
              ),
            }
          : current,
      );
      return true;
    } catch (e) {
      if (e.status === 401) invalidate();
      setNotice(
        e.status === 401
          ? "로그인이 만료됐어요. 다시 로그인해주세요."
          : "리뷰를 불러오지 못했어요. 서버 연결을 확인해주세요.",
      );
      return false;
    } finally {
      reviewRequestCount.current -= 1;
      setLoadingReviews(reviewRequestCount.current > 0);
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
    }).then((data) => {
      if (!data) return false;
      setState((state) =>
        state.owner === user?.id
          ? {
              ...state,
              records: state.records.map((item) =>
                item.id === id
                  ? withBookReview(data.record, {
                      rating: item.rating || 0,
                      content: item.content || "",
                      has_spoiler: item.hasSpoiler || false,
                    })
                  : item,
              ),
            }
          : state,
      );
      return true;
    });
  }
  function updateReview(id, patch) {
    const current = records.find((item) => item.id === id);
    if (!current) return Promise.resolve(false);
    return save(`/api/library/${encodeURIComponent(id)}/review`, "PUT", {
      star: patch.rating || 0,
      content: patch.content || "",
      has_spoiler: false,
    }).then((data) => {
      if (!data) return false;
      setState((state) =>
        state.owner === user?.id
          ? {
              ...state,
              records: state.records.map((item) =>
                item.id === id
                  ? withBookReview(data.record, {
                      rating: data.record.rating,
                      content: data.record.content,
                      has_spoiler: data.record.has_spoiler || false,
                    })
                  : item,
              ),
            }
          : state,
      );
      return true;
    });
  }
  function updateLog(id, day, memo, readingMinutes = null) {
    if (!records.some((record) => record.id === id)) {
      setNotice("서재에서 책을 찾지 못했어요.");
      return Promise.resolve(false);
    }
    const url = `/api/library/${encodeURIComponent(id)}/logs/${encodeURIComponent(day)}`;
    const deleting = memo === null;
    return save(
      url,
      deleting ? "DELETE" : "PUT",
      deleting
        ? undefined
        : { content: memo, reading_minutes: readingMinutes },
    ).then((data) => {
      if (!data) return false;
      setState((state) =>
        state.owner === user?.id
          ? {
              ...state,
              records: state.records.map((item) =>
                item.id === id ? { ...item, ...data.record } : item,
              ),
            }
          : state,
      );
      return true;
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
      value={{
        records,
        add,
        update,
        updateReview,
        updateLog,
        loadDailyLog,
        loadBookReview: loadBookReviewForRecord,
        remove,
        notice,
        busy,
        loadingLogs,
        loadingReviews,
        loading: false,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export const useLibrary = () => useContext(Context);
