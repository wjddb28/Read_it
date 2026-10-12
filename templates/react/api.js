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
export function searchBooks({ query, natural, by = "title", page = 1 }, signal) {
  return natural
    ? request(
        "/api/search?" +
          new URLSearchParams({
            q: query,
            ai: "true",
            top_k: "5",
            comment: "true",
          }),
        { signal },
      )
    : request(
        "/api/books/search?" +
          new URLSearchParams({ q: query, by, page: String(page), size: "20" }),
        { signal },
      );
}
