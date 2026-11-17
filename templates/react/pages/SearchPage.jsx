import { useSearchParams } from "react-router-dom";
import PopularBooks from "../components/PopularBooks";
import SearchPanel from "../components/SearchPanel";
export default function SearchPage() {
  const [params] = useSearchParams();
  return (
    <main className="container workspace-page">

      <h1>도서 검색</h1>

      <SearchPanel />
      {!params.get("q")?.trim() && <PopularBooks />}
    </main>
  );
}
