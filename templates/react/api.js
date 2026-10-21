export async function request(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(
      typeof data?.detail === "string"
        ? data.detail
        : `요청 실패 (${response.status}). 서버 설정을 확인해주세요.`,
    );
    error.status = response.status;
    throw error;
  }
  if (data === null)
    throw new Error("JSON 응답이 없어요. API 주소를 확인해주세요.");
  return data;
}
const naturalCache = new Map();
export async function searchBooks({ query, natural, by = "title", page = 1, sort = "popular", withComment = true }, signal) {
  const cacheKey = JSON.stringify([query, withComment]);
  const cached = naturalCache.get(cacheKey);
  if (natural && cached?.expires > Date.now()) return cached.data;
  const data = await (natural
    ? request(
        "/api/search?" +
          new URLSearchParams({
            q: query,
            ai: "true",
            top_k: "20",
            comment: String(withComment),
          }),
        { signal },
      )
    : request(
        "/api/catalog/search?" +
          new URLSearchParams({ q: query, by, page: String(page), sort, size: "10" }),
        { signal },
      ));
  if (natural) {
    naturalCache.set(cacheKey, { data, expires: Date.now() + 300000 });
    if (naturalCache.size > 8) naturalCache.delete(naturalCache.keys().next().value);
  }
  return data;
}

const detailCache = new Map();
export function getBookDetail(isbn) {
  const cached = detailCache.get(isbn);
  if (cached?.expires > Date.now()) return cached.promise;
  const promise = request("/api/books/" + encodeURIComponent(isbn)).catch((error) => {
    detailCache.delete(isbn);
    throw error;
  });
  detailCache.set(isbn, { promise, expires: Date.now() + 60000 });
  if (detailCache.size > 200) detailCache.delete(detailCache.keys().next().value);
  return promise;
}
