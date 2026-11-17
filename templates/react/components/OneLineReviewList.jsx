import CopyComment from './CopyComment';

function reviewDate(value) {
  if (value == null || value === '') return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return { value: date.toISOString(), label: new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Asia/Seoul',
  }).format(date) };
}

export default function OneLineReviewList({ lines, showBook = false }) {
  return <div className="one-line-review-list">{lines.map(line => {
    const rating = Math.max(0, Math.min(5, Math.floor(Number(line.rating) || 0)));
    const date = reviewDate(line.createdAt);
    return <article className="one-line-review-card" key={line.id}>
      {showBook && line.book && <strong className="one-line-review-book">『{line.book.title}』</strong>}
      <div className="one-line-review-body">{line.hasSpoiler
        ? <details><summary>스포일러가 포함된 한줄평 보기</summary><CopyComment text={line.body} /></details>
        : <CopyComment text={line.body} />}</div>
      <div className="one-line-review-meta">
        <span>{line.author?.nickname || '독자'}</span>
        {rating > 0 && <span className="one-line-review-stars" role="img" aria-label={`평점 ${rating}점 / 5점`}>
          <span aria-hidden="true">{'★'.repeat(rating)}</span><span className="empty-stars" aria-hidden="true">{'★'.repeat(5 - rating)}</span>
        </span>}
        {line.recommended != null && <span>{line.recommended ? '추천해요' : '추천하지 않아요'}</span>}
        {date && <time dateTime={date.value}>{date.label}</time>}
      </div>
    </article>;
  })}</div>;
}
