import { useSearchParams } from "react-router-dom";
import PopularBooks from "../components/PopularBooks";
import SearchPanel from "../components/SearchPanel";
export default function SearchPage() {
  const [params] = useSearchParams();
  return (
    <main className="container workspace-page">
      <p className="section-kicker">DISCOVER</p>
      <h1>도서 검색</h1>
      <p className="page-subtitle">제목으로 찾고, 원하는 이야기로 발견해요.</p>
      <SearchPanel />
      {!params.get("q")?.trim() && <PopularBooks />}
    </main>
  );
}
