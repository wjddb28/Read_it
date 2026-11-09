export default function Pagination({ page, pages, onChange }) {
  if (pages <= 1) return null;
  const numbers = [...new Set([1, pages, ...Array.from({ length: 5 }, (_, i) => page + i - 2)])]
    .filter((value) => value >= 1 && value <= pages).sort((a, b) => a - b);
  return <nav className="pagination numbered-pagination" aria-label="페이지 이동">
    <button type="button" disabled={page <= 1} onClick={() => onChange(1)}>맨 앞</button>
    <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>이전</button>
    {numbers.map((number, i) => <span className="page-number-slot" key={number}>
      {i > 0 && number - numbers[i - 1] > 1 && <span aria-hidden="true">…</span>}
      <button type="button" aria-label={`${number}페이지`} aria-current={page === number ? 'page' : undefined}
        onClick={() => onChange(number)}>{number}</button>
    </span>)}
    <button type="button" disabled={page >= pages} onClick={() => onChange(page + 1)}>다음</button>
    <button type="button" disabled={page >= pages} onClick={() => onChange(pages)}>맨 뒤</button>
    <span className="sr-only">전체 {pages}페이지 중 {page}페이지</span>
  </nav>;
}
