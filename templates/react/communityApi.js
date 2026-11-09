import { request } from "./api";
export function community(path, options = {}) { return request('/api/community' + path, options); }
export function sendCommunity(path, body, method = 'POST') {
  return community(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
}
export function bookReference(book) {
  return { isbn: String(book.isbn), title: book.title, author: book.author || '',
    cover_image_url: book.cover_image_url || null,
    genres: Array.isArray(book.genres) ? book.genres : [book.genre, ...(book.subgenres || '').split('|')].filter(Boolean) };
}
export const categoryLabels = { talk: '잡담', share: '책 공유', info: '책 정보' };
export const stageLabels = ['초반', '중반', '결말'];
