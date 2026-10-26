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
const sortLabels = { popular: "인기순", title: "가나다순", recent: "최신순" };
function orderBooks(books, sort) {
  const number = (value) => value == null || !Number.isFinite(Number(value)) ? -1 : Number(value);
  return [...books].sort((a, b) => {
    const field = sort === "popular" ? "loan_count" : sort === "recent" ? "publish_year" : null;
    const difference = field ? number(b[field]) - number(a[field]) : 0;
    return difference || (a.title || "").localeCompare(b.title || "", "ko") ||
      (a.author || "").localeCompare(b.author || "", "ko");
  });
}
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
  const routeSort = sortLabels[params.get("sort")] ? params.get("sort") : "popular";
  const routeNoKids = params.get("nokids") === "1";
  const [noKids, setNoKids] = useState(routeNoKids);
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
    setNoKids(routeNoKids);
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
      sort: routeSort,
      noKids: routeNoKids,
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
        const combined = books;
        const seen = new Set();
        const unique = combined.filter((book) => {
          const key = book.isbn || `${book.title}|${book.author}`;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        const ordered = orderBooks(unique, search.sort);
        const page = search.natural ? Math.min(search.page, Math.max(1, Math.ceil(ordered.length / 10))) : Number(data.page) || search.page;
        setResult({
          books: search.natural ? ordered.slice((page - 1) * 10, page * 10) : books,
          total: search.natural ? ordered.length : Number(data.total) || 0,
          pages:
            (search.natural ? Math.ceil(ordered.length / 10) : Number(data.total_pages)) ||
            Math.ceil((Number(data.total) || 0) / 10),
          comment: data.ai_comment,
          recommendations: Array.isArray(data.recommendations) ? data.recommendations : [],
          commentSource: data.comment_source,
          message: data.message,
          similarTo: data.similar_to,
          corrected: data.corrected_query,
          capped: !search.natural && !!data.capped,
          cap: Number(data.cap) || 1000,
          search: { ...search, page },
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
  }, [home, routeQuery, routeAI, routeBy, routePage, routeSort, routeNoKids, retry]);
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
      sort: routeSort,
      ...(noKids && !natural ? { nokids: "1" } : {}),
    });
    if (home) navigate("/search?" + next);
    else if (next.toString() === params.toString()) {
      setRetry((n) => n + 1);
    } else setParams(next);
  }
  const pageTo = (page) =>
    setParams({
      q: result.search.query,
      mode: result.search.natural ? "ai" : "normal",
      by: result.search.by,
      page: String(page),
      sort: result.search.sort,
      ...(result.search.noKids ? { nokids: "1" } : {}),
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
        {!natural && (
          <label className="no-kids-option">
            <input
              type="checkbox"
              checked={noKids}
              onChange={(e) => {
                setNoKids(e.target.checked);
                if (!home && routeQuery.trim()) // 검색 결과가 있으면 바로 다시 검색
                  setParams({ q: routeQuery, mode: "normal", by: routeBy, page: "1", sort: routeSort,
                    ...(e.target.checked ? { nokids: "1" } : {}) });
              }}
            />
            어린이 책 빼고 보기
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
            {loading ? "도서를 검색하고 있어요… 처음 검색할 때는 전체 목록 정리에 시간이 걸릴 수 있어요." : error}
          </div>
          {result ? (
            <section className="search-results" aria-label="검색 결과">
              <div className="section-title-row">
                <h2>
                  {result.search.natural ? "자연어 추천 결과" : "검색 결과"}
                </h2>
                <span>
                  {result.search.natural ? `추천 결과 전체 ${result.total}권` : `검색 결과 전체 ${result.total}권`} · 10권씩
                </span>
                <label className="result-sort">정렬
                  <select aria-label="검색 결과 정렬" value={routeSort} onChange={(event) => setParams({
                    q: routeQuery, mode: routeAI ? "ai" : "normal", by: routeBy,
                    sort: event.target.value, page: "1", ...(routeNoKids ? { nokids: "1" } : {}),
                  })}>
                    {Object.entries(sortLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
              </div>
              <p className="sort-description">{routeSort === "popular"
                ? "대출수 기준으로 정렬해요. 대출수 정보가 없는 책은 뒤에 표시돼요."
                : routeSort === "recent" ? "출판연도가 최근인 책부터 보여줘요." : "책 제목을 가나다순으로 보여줘요."}</p>
              {result.similarTo && (
                <p className="similar-banner">
                  『{result.similarTo.title}』
                  {result.similarTo.author && ` (${result.similarTo.author})`} 기준으로
                  비슷한 책을 골랐어요.
                </p>
              )}
              {result.corrected && (
                <p className="corrected-query">
                  '{result.corrected}' 표기로 찾은 결과예요.
                </p>
              )}
              {(result.message || !result.books.length) && (
                <p role="status">{result.message || "검색 결과가 없어요."}</p>
              )}
              {result.search.natural && result.books.length > 0 && (
                <div className="ai-comment">
                  <h3>{result.commentSource === "catalog" ? "추천 도서 안내" : "AI 추천 코멘트"}</h3>
                  {result.recommendations.length ? <ul className="recommendation-comments">
                    {result.recommendations.map((entry) => <li key={entry.isbn}>
                      <a href={`#book-${entry.isbn}`}>『{entry.title}』</a>
                      <p>{entry.reason}</p>
                    </li>)}
                  </ul> : <p>{result.comment?.replace(/\*\*/g, "") ||
                    "추천 코멘트를 불러오지 못했지만 도서 목록은 확인할 수 있어요."}</p>}
                  {result.commentSource === "catalog" && <small>AI 코멘트 생성이 지연되어 책 정보로 안내하고 있어요.</small>}
                </div>
              )}
              <div className="result-list">
                {result.books.map((book, i) => (
                  <BookCard
                    key={`${result.search.page}-${book.isbn || i}`}
                    book={book}
                  />
                ))}
              </div>
              {result.capped && result.search.page >= result.pages && (
                <p className="capped-notice">
                  검색 결과가 많아 인기 상위 {result.cap.toLocaleString()}권 안에서 보여드렸어요.
                  원하는 도서가 없다면 더 구체적인 키워드나 작가 이름으로 검색해 주세요.
                </p>
              )}
              {result.pages > 1 && (
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
