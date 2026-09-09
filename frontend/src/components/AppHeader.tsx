import { ChevronDownIcon } from "./Icons";

export default function AppHeader() {
  return (
    <header className="app-header">
      <button type="button" className="assistant-menu">
        Trợ lý Luật Giao thông <ChevronDownIcon />
      </button>
    </header>
  );
}
