import { request } from "../api";
import { useAuth } from "../components/AuthContext";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Modal from "../components/Modal";
import "../../../static/css/react/community.css";
const KEY = "readit.community.v1";
const categories = {
  ALL: "전체 이야기",
  모임: "독서 모임",
  블로그: "독서노트",
  대화: "질문·추천",
};
const examples = [
  {
    id: "new-example1",
    kind: "모임",
    title: "한 달에 한 권, 부담 없이 함께 읽어요",
    tags: "함께읽기 소설",
    book: "불편한 편의점",
    body: "읽는 속도가 달라도 괜찮아요. 한 달 동안 책 한 권을 읽고, 마음에 남은 장면을 함께 이야기해보는 모임이에요.",
    author: "Read-it 예시",
    comments: [],
    sample: true,
  },
  {
    id: "new-example2",
    kind: "블로그",
    title: "책을 덮고도 오래 남는 문장들",
    tags: "독서기록 문장수집",
    book: "어린 왕자",
    body: "줄거리보다 한 문장이 오래 기억에 남을 때가 있어요. 이번 독서에서는 내가 왜 그 문장에 멈췄는지 짧게 기록해봤어요.",
    author: "Read-it 예시",
    comments: [],
    sample: true,
  },
  {
    id: "new-example3",
    kind: "대화",
    title: "독서가 오랜만인데, 어떤 책부터 읽을까요?",
    tags: "입문 추천",
    book: "다음에 읽을 책",
    body: "짧은 시간에도 편하게 읽을 수 있는 책을 찾고 있어요. 여러분이 독서를 다시 시작할 때 좋았던 책을 알려주세요.",
    author: "Read-it 예시",
    comments: [],
    sample: true,
  },
  {
    id: "new-example4",
    kind: "블로그",
    title: "정답보다 질문이 많아지는 책",
    tags: "고전 감상",
    book: "데미안",
    body: "읽을 때마다 다른 부분이 눈에 들어와요. 이번에는 등장인물보다 내가 어떤 선택을 하고 싶은지 생각하게 됐어요.",
    author: "Read-it 예시",
    comments: [],
    sample: true,
  },
  {
    id: "new-example5",
    kind: "모임",
    title: "주말 20분, 조용히 읽는 시간",
    tags: "독서습관 함께읽기",
    book: "각자 고른 책",
    body: "같은 책을 읽지 않아도 좋아요. 각자 고른 책으로 읽는 시간을 만들고, 한 줄의 감상을 나누는 모임이에요.",
    author: "Read-it 예시",
    comments: [],
    sample: true,
  },
  {
    id: "new-example6",
    kind: "대화",
    title: "책 속 인물 한 명을 만날 수 있다면?",
    tags: "자유대화 소설",
    book: "책 속으로",
    body: "어떤 인물을 만나서 무슨 이야기를 하고 싶나요? 책을 읽으며 궁금했던 질문을 나눠봐요.",
    author: "Read-it 예시",
    comments: [],
    sample: true,
  },
];
function load(userId) {
  if (!userId) return examples;
  try {
    const saved = JSON.parse(
      localStorage.getItem(KEY + ":" + userId) || "null",
    );
    return Array.isArray(saved)
      ? saved
          .filter(
            (p) =>
              p &&
              p.id &&
              typeof p.title === "string" &&
              Array.isArray(p.comments),
          )
          .map((p) => ({
            ...p,
            tags: typeof p.tags === "string" ? p.tags : "",
            body: typeof p.body === "string" ? p.body : "",
          }))
      : examples;
  } catch {
    return examples;
  }
}
export default function CommunityPage() {
  const { user, invalidate } = useAuth();
  const owner = useRef(user?.id);
  owner.current = user?.id;
  const [posts, setPosts] = useState(() => load(user?.id)),
    [tab, setTab] = useState("ALL"),
    [query, setQuery] = useState(""),
    [sort, setSort] = useState("recent"),
    [onlySaved, setOnlySaved] = useState(false),
    [creating, setCreating] = useState(false),
    [selected, setSelected] = useState(null),
    [notice, setNotice] = useState(""),
    [comment, setComment] = useState("");
  useEffect(() => {
    setPosts(load(user?.id));
    setSelected(null);
    setCreating(false);
    setNotice("");
  }, [user?.id]);
  const post = posts.find((p) => p.id === selected);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = posts.filter(
      (p) =>
        (tab === "ALL" || p.kind === tab) &&
        (!onlySaved || p.saved) &&
        (!q ||
          `${p.title} ${p.body} ${p.tags} ${p.book || ""}`
            .toLowerCase()
            .includes(q)),
    );
    return sort === "comments"
      ? [...filtered].sort((a, b) => b.comments.length - a.comments.length)
      : filtered;
  }, [posts, tab, query, sort, onlySaved]);
  async function save(next) {
    if (!user) {
      setNotice("로그인 후 저장할 수 있어요.");
      return false;
    }
    try {
      const session = await request("/api/auth/me");
      if (session.user.id !== user.id || owner.current !== user.id)
        return false;
      localStorage.setItem(KEY + ":" + user.id, JSON.stringify(next));
      setPosts(next);
      setNotice("이 브라우저에 저장했어요.");
      return true;
    } catch (e) {
      if (e.status === 401) invalidate();
      setNotice(
        "저장하지 못했어요. 로그인과 서버 연결, 저장 공간을 확인해주세요.",
      );
      return false;
    }
  }
  function show(id) {
    setSelected(id);
    setComment("");
  }
  async function create(e) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const title = String(f.get("title")).trim(),
      body = String(f.get("body")).trim();
    if (!title || !body) {
      setNotice("제목과 내용을 입력해주세요.");
      return;
    }
    const next = {
      id: crypto.randomUUID(),
      kind: String(f.get("kind")),
      title,
      body,
      tags: String(f.get("tags")).trim(),
      book: String(f.get("book")).trim() || "나의 책 이야기",
      author: user?.nickname || "나",
      comments: [],
      sample: false,
      saved: false,
      createdAt: Date.now(),
    };
    if (await save([next, ...posts])) {
      setCreating(false);
      setTab("ALL");
      setOnlySaved(false);
      setQuery("");
      setSort("recent");
    }
  }
  async function addComment(e) {
    e.preventDefault();
    if (!comment.trim()) return;
    if (
      await save(
        posts.map((p) =>
          p.id === selected
            ? {
                ...p,
                comments: [
                  ...p.comments,
                  { id: crypto.randomUUID(), text: comment.trim() },
                ],
              }
            : p,
        ),
      )
    )
      setComment("");
  }
  const savedCount = posts.filter((p) => p.saved).length;
  return (
    <main className="container commune-page">
      <section className="commune-hero">
        <div>
          <p className="section-kicker">BETWEEN THE PAGES</p>
          <h1>
            책 다음은,
            <br />
            우리의 이야기.
          </h1>
          <p>함께 읽을 사람을 만나고, 오래 남은 생각을 나눠요.</p>
          <button
            className="primary-btn"
            onClick={() => {
              setNotice("");
              setCreating(true);
            }}
          >
            이야기 쓰기 <span aria-hidden="true">＋</span>
          </button>
        </div>
        <div className="commune-art" aria-hidden="true">
          <div className="art-book art-one">
            READ
            <br />
            TOGETHER
          </div>
          <div className="art-book art-two">
            한 권의 책,
            <br />
            여러 개의 시선
          </div>
          <span className="art-note">어떤 페이지에 머물렀나요?</span>
        </div>
      </section>
      <div className="commune-layout">
        <section className="commune-feed" aria-label="독서 이야기 목록">
          <div className="commune-tabs" role="group" aria-label="이야기 종류">
            {Object.entries(categories).map(([value, label]) => (
              <button
                key={value}
                aria-pressed={tab === value}
                onClick={() => setTab(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="commune-controls">
            <label className="commune-search">
              <span className="sr-only">이야기 검색</span>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="궁금한 책이나 이야기를 찾아보세요"
                type="search"
              />
            </label>
            <label>
              <span className="sr-only">이야기 정렬</span>
              <select value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="recent">최근 작성순</option>
                <option value="comments">댓글 많은순</option>
              </select>
            </label>
          </div>
          <div className="commune-feed-heading">
            <p>
              {onlySaved ? "관심 표시한 이야기" : "함께 나누는 이야기"}{" "}
              <strong>{visible.length}</strong>
            </p>
            {onlySaved && (
              <button className="text-btn" onClick={() => setOnlySaved(false)}>
                전체 보기
              </button>
            )}
          </div>
          <p className="commune-local">
            예시와 이 브라우저에 저장한 글이에요. 다른 사용자에게 공유되지는
            않아요.
          </p>
          <p className="commune-status" role="status">
            {notice}
          </p>
          {visible.length ? (
            <div className="commune-cards">
              {visible.map((p) => (
                <article className={"commune-card kind-" + p.kind} key={p.id}>
                  <div className="commune-card-top">
                    <span className="commune-kind">
                      {categories[p.kind] || p.kind}
                    </span>
                    <button
                      className={"commune-save " + (p.saved ? "is-saved" : "")}
                      aria-pressed={!!p.saved}
                      aria-label={`${p.title} 관심 표시`}
                      onClick={() =>
                        save(
                          posts.map((item) =>
                            item.id === p.id
                              ? { ...item, saved: !item.saved }
                              : item,
                          ),
                        )
                      }
                    >
                      {p.saved ? "★" : "☆"}
                    </button>
                  </div>
                  <h2>
                    <button onClick={() => show(p.id)}>{p.title}</button>
                  </h2>
                  <p className="commune-excerpt">{p.body}</p>
                  <div className="commune-book-strip">
                    <span className="commune-book-icon" aria-hidden="true">
                      책
                    </span>
                    <span>{p.book || "독서 이야기"}</span>
                  </div>
                  <div className="commune-tags">
                    {p.tags
                      .split(/\s+/)
                      .filter(Boolean)
                      .slice(0, 4)
                      .map((tag, i) => (
                        <button
                          key={i}
                          onClick={() => {
                            setTab("ALL");
                            setQuery(tag.replace(/^#/, ""));
                          }}
                        >
                          #{tag.replace(/^#/, "")}
                        </button>
                      ))}
                  </div>
                  <div className="commune-card-footer">
                    <span>
                      {p.author || "브라우저 기록"}
                      {p.sample ? " · 예시" : ""}
                    </span>
                    <button onClick={() => show(p.id)}>
                      댓글 {p.comments.length} →
                    </button>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <h2>아직 이야기가 없어요</h2>
              <p>검색 조건을 바꾸거나 첫 이야기를 남겨보세요.</p>
              <button
                className="outline-btn"
                onClick={() => {
                  setQuery("");
                  setTab("ALL");
                  setOnlySaved(false);
                }}
              >
                전체 이야기 보기
              </button>
            </div>
          )}
        </section>
        <aside className="commune-sidebar">
          <div className="commune-side-card">
            <span className="section-kicker">YOUR CORNER</span>
            <h2>나의 작은 책모임</h2>
            <p>
              새로운 이야기를 남기거나,
              <br />
              다시 보고 싶은 글을 모아보세요.
            </p>
            <div className="commune-mini-stats">
              <div>
                <strong>{posts.filter((p) => !p.sample).length}</strong>
                <span>내가 쓴 글</span>
              </div>
              <div>
                <strong>{savedCount}</strong>
                <span>관심 이야기</span>
              </div>
            </div>
            <button
              className="outline-btn"
              aria-pressed={onlySaved}
              onClick={() => {
                setOnlySaved(!onlySaved);
                setTab("ALL");
                setQuery("");
              }}
            >
              {onlySaved ? "전체 이야기 보기" : "관심 이야기 모아보기"}
            </button>
          </div>
          <div className="commune-question">
            <span>오늘의 질문</span>
            <h2>
              누군가에게 꼭 건네고 싶은
              <br />책 한 권이 있나요?
            </h2>
            <p>제목과 짧은 이유를 남겨주세요.</p>
            <button
              onClick={() => {
                setTab("대화");
                setCreating(true);
              }}
            >
              내 이야기 남기기 →
            </button>
          </div>
          <div className="commune-side-card commune-topics">
            <h2>이런 이야기는 어때요?</h2>
            {["함께읽기", "소설", "독서기록", "추천"].map((tag) => (
              <button
                key={tag}
                onClick={() => {
                  setQuery(tag);
                  setTab("ALL");
                  setOnlySaved(false);
                }}
              >
                #{tag}
              </button>
            ))}
          </div>
          <Link className="commune-discover" to="/search">
            이야기할 책 찾으러 가기 →
          </Link>
        </aside>
      </div>
      <Modal
        open={creating}
        close={() => setCreating(false)}
        title="나의 책 이야기"
      >
        <form className="editor-form" onSubmit={create}>
          <label>
            이야기 종류
            <select name="kind" defaultValue={tab === "ALL" ? "블로그" : tab}>
              {Object.entries(categories)
                .filter(([key]) => key !== "ALL")
                .map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
            </select>
          </label>
          <label>
            제목
            <input
              name="title"
              required
              maxLength={120}
              placeholder="어떤 이야기를 나누고 싶나요?"
            />
          </label>
          <label>
            함께 이야기할 책
            <input name="book" maxLength={100} placeholder="책 제목 (선택)" />
          </label>
          <label>
            태그
            <input
              name="tags"
              maxLength={150}
              placeholder="예: 소설 감상 함께읽기"
            />
          </label>
          <label>
            내용
            <textarea
              name="body"
              required
              rows={6}
              maxLength={3000}
              placeholder="기억에 남은 장면, 모임 소개, 궁금한 이야기를 적어주세요."
            />
          </label>
          <button className="primary-btn">브라우저에 저장</button>
          <p role="status">{notice}</p>
        </form>
      </Modal>
      <Modal
        open={!!post}
        close={() => setSelected(null)}
        title={post?.title || "책 이야기"}
      >
        {post && (
          <>
            <div className="commune-detail-meta">
              <span className="commune-kind">
                {categories[post.kind] || post.kind}
              </span>
              <span>
                {post.author}
                {post.sample ? " · 예시" : ""}
              </span>
            </div>
            <p className="detail-body">{post.body}</p>
            <div className="commune-book-strip">
              함께 이야기하는 책 · {post.book}
            </div>
            <h3 className="commune-comment-title">
              댓글 {post.comments.length}
            </h3>
            <div className="comment-list">
              {post.comments.map((c) => (
                <p key={c.id}>
                  <strong>나 · 브라우저 기록</strong>
                  <br />
                  {c.text}
                </p>
              ))}
            </div>
            <form className="editor-form" onSubmit={addComment}>
              <label>
                생각 나누기
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  required
                  maxLength={1000}
                  rows={3}
                  placeholder="이 이야기를 읽고 떠오른 생각을 남겨주세요."
                />
              </label>
              <button className="primary-btn">댓글 저장</button>
              <p role="status">{notice}</p>
            </form>
          </>
        )}
      </Modal>
    </main>
  );
}
