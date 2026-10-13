import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { searchBooks } from "../api";
import BookCard from "./BookCard";
const labels = {
  all: "전체",
  title: "제목",
  author: "저자",
  isbn: "ISBN",
  keyword: "키워드",
};
export default function SearchPanel({ home = false }) {
  const navigate = useNavigate(),
    [params, setParams] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") || ""),
    [natural, setNatural] = useState(params.get("mode") === "ai"),
    [by, setBy] = useState(labels[params.get("by")] ? params.get("by") : "title");
  const [result, setResult] = useState(null),
    [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  const active = useRef(null),
    input = useRef(null);
  const routeQuery = params.get("q") || "",
    routeAI = params.get("mode") === "ai",
    routeBy = labels[params.get("by")] ? params.get("by") : "title",
    routePage = Number.isSafeInteger(Number(params.get("page")))
      ? Math.max(1, Number(params.get("page")))
      : 1;
  function reset() {
    active.current?.abort();
    active.current = null;
    setLoading(false);
    setResult(null);
    setError("");
  }
  function switchMode(value) {
    reset();
    setNatural(value);
    input.current?.focus();
  }
  useEffect(() => {
    const fn = () => navigate("/search?mode=ai");
    window.addEventListener("readit:ai-search", fn);
    return () => window.removeEventListener("readit:ai-search", fn);
  }, [navigate]);
  useEffect(() => {
    if (home) return;
    setQuery(routeQuery);
    setNatural(routeAI);
    setBy(routeBy);
    if (!routeQuery.trim()) {
      reset();
      return;
    }
    const controller = new AbortController();
    active.current = controller;
    setLoading(true);
    setResult(null);
    setError("");
    const search = {
      query: routeQuery,
      natural: routeAI,
      by: routeBy,
      page: routePage,
    };
    searchBooks(search, controller.signal)
      .then((data) => {
        if (active.current !== controller) return;
        const books = Array.isArray(data.books)
          ? data.books
          : search.natural && Array.isArray(data.data)
            ? data.data
            : null;
        if (!books) throw new Error("도서 목록 응답 형식을 확인해주세요.");
        setResult({
          books,
          total: search.natural ? books.length : Number(data.total) || 0,
          pages:
            Number(data.total_pages) ||
            Math.ceil((Number(data.total) || 0) / 20),
          estimate: !!data.total_is_estimate,
          comment: data.ai_comment,
          message: data.message,
          similarTo: data.similar_to,
          sameAuthor: Array.isArray(data.same_author) ? data.same_author : [],
          search,
        });
      })
      .catch((e) => {
        if (e.name !== "AbortError" && active.current === controller)
          setError(e.message || "서버에 연결하지 못했어요.");
      })
      .finally(() => {
        if (active.current === controller) setLoading(false);
      });
    return () => {
      controller.abort();
      if (active.current === controller) active.current = null;
    };
  }, [home, routeQuery, routeAI, routeBy, routePage, retry]);
  function submit(e) {
    e.preventDefault();
    if (!query.trim()) {
      setError("검색어를 입력해주세요.");
      return;
    }
    const next = new URLSearchParams({
      q: query.trim(),
      mode: natural ? "ai" : "normal",
      by,
      page: "1",
    });
    if (home) navigate("/search?" + next);
    else if (next.toString() === params.toString()) {
      setRetry((n) => n + 1);
    } else setParams(next);
  }
  const pageTo = (page) =>
    setParams({
      q: result.search.query,
      mode: "normal",
      by: result.search.by,
      page: String(page),
    });
  return (
    <div id="search">
      <form
        className={"search-box " + (natural ? "is-natural" : "")}
        onSubmit={submit}
      >
        <label className="sr-only" htmlFor="bookQuery">
          검색어
        </label>
        <input
          ref={input}
          id="bookQuery"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          required
          maxLength={500}
          placeholder={
            natural
              ? "예: 비 오는 날 읽기 좋은 따뜻한 소설"
              : by === "all"
                ? "책 제목, 저자, 키워드, ISBN을 검색해보세요"
                : `${labels[by]}을 검색해보세요`
          }
          aria-describedby="searchHelp"
        />
        <button
          className="natural-toggle"
          type="button"
          aria-pressed={natural}
          onClick={() => switchMode(!natural)}
        >
          자연어 검색
        </button>
        <button disabled={loading}>{loading ? "검색 중…" : "검색"}</button>
      </form>
      <div className="search-options">
        {!natural && (
          <label>
            검색 기준{" "}
            <select
              value={by}
              onChange={(e) => {
                reset();
                setBy(e.target.value);
              }}
            >
              {Object.entries(labels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        )}
        <p id="searchHelp">
          {natural
            ? "원하는 분위기나 관심사를 문장으로 적어주세요."
            : by === "all"
              ? "제목·저자·키워드를 함께 검색해요. ISBN 입력도 가능해요."
              : `정보나루에서 ${labels[by]} 기준으로 검색해요.`}
        </p>
      </div>
      {!home && (
        <>
          <div
            role="status"
            aria-live="polite"
            className={error ? "search-message error" : "search-message"}
          >
            {loading ? "도서를 검색하고 있어요…" : error}
          </div>
          {result ? (
            <section className="search-results" aria-label="검색 결과">
              <div className="section-title-row">
                <h2>
                  {result.search.natural ? "자연어 추천 결과" : "검색 결과"}
                </h2>
                <span>
                  {result.search.natural
                    ? `추천 ${result.books.length}권`
                    : result.estimate
                      ? `통합 검색 · 현재 ${result.books.length}권`
                      : `전체 ${result.total}건 · 현재 ${result.books.length}권`}
                </span>
              </div>
              {result.similarTo && (
                <p className="similar-banner">
                  『{result.similarTo.title}』
                  {result.similarTo.author && ` (${result.similarTo.author})`} 기준으로
                  비슷한 책을 골랐어요. 같은 작가·시리즈는 아래에 따로 모았어요.
                </p>
              )}
              {(result.message || !result.books.length) && (
                <p role="status">{result.message || "검색 결과가 없어요."}</p>
              )}
              <div className="result-list">
                {result.books.map((book, i) => (
                  <BookCard
                    key={`${result.search.page}-${book.isbn || i}`}
                    book={book}
                  />
                ))}
              </div>
              {result.sameAuthor.length > 0 && (
                <section className="same-author" aria-label="같은 작가·시리즈">
                  <h3>같은 작가·시리즈</h3>
                  <div className="result-list">
                    {result.sameAuthor.map((book, i) => (
                      <BookCard key={`same-${book.isbn || i}`} book={book} />
                    ))}
                  </div>
                </section>
              )}
              {result.search.natural && result.books.length > 0 && (
                <div className="ai-comment">
                  <h3>AI 추천 코멘트</h3>
                  <p>
                    {result.comment ||
                      "추천 코멘트를 불러오지 못했지만 도서 목록은 확인할 수 있어요."}
                  </p>
                </div>
              )}
              {!result.search.natural && result.pages > 1 && (
                <div className="pagination">
                  <button
                    type="button"
                    disabled={result.search.page <= 1}
                    onClick={() => pageTo(result.search.page - 1)}
                  >
                    이전
                  </button>
                  <span>
                    {result.search.page} / {result.pages}
                  </span>
                  <button
                    type="button"
                    disabled={result.search.page >= result.pages}
                    onClick={() => pageTo(result.search.page + 1)}
                  >
                    다음
                  </button>
                </div>
              )}
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
