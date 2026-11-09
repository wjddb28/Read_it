import { useState } from 'react';
export const genreGroups = {
  '문학': ['소설(일반문학)', '고전소설', '추리·미스터리', 'SF', '판타지', '로맨스', '공포·스릴러', '시', '에세이', '성장', '가족·일상', '힐링·휴먼'],
  '인문·사회': ['인문', '역사', '철학', '사회·정치', '종교학', '기독교', '불교'],
  '실용·교양': ['경제·경영', '마케팅', '과학(일반)', '뇌과학', '물리학', '천문학', '진화론', '생물학', '자기계발', '심리학', '투자', '예술·문화(일반)', '음악', '미술', '미학', '여행', '건강·의학'],
  '전문·기타': ['IT·컴퓨터', '교육', '외국어', '육아'],
};
export default function GenrePicker({ label, value, onChange, excluded = [] }) {
  const [custom, setCustom] = useState('');
  function toggle(genre) { onChange(value.includes(genre) ? value.filter((item) => item !== genre) : [...value, genre]); }
  return <section className="genre-picker" aria-label={label}>
    <div className="section-title-row"><h3>{label}</h3><small>{value.length}개 선택</small></div>
    {value.length > 0 && <div className="selected-genres">{value.map((genre) => <button type="button" key={genre} onClick={() => toggle(genre)}>{genre} ×</button>)}</div>}
    {Object.entries(genreGroups).map(([group, genres]) => <div className="genre-group" key={group}><h4>{group}</h4>
      <div className="genre-chips">{genres.map((genre) => <button key={genre} type="button" aria-pressed={value.includes(genre)}
        disabled={!value.includes(genre) && (excluded.includes(genre) || value.length >= 40)} onClick={() => toggle(genre)}>{genre}</button>)}</div></div>)}
    <label>기타 장르 직접 입력<div className="genre-custom"><input aria-label={`${label} 직접 입력`} maxLength={30} value={custom} onChange={(event) => setCustom(event.target.value)} placeholder="목록에 없는 장르 (최대 30자)" />
      <button type="button" className="outline-btn" disabled={!custom.trim() || excluded.includes(custom.trim()) || value.length >= 40}
        onClick={() => { if (!value.includes(custom.trim())) onChange([...value, custom.trim()]); setCustom(''); }}>추가</button></div></label>
  </section>;
}
