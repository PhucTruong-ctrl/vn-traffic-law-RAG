import { ChevronDown } from "lucide-react";

export default function AppHeader() {
  return (
    <header className="app-header">
      <button
        type="button"
        className="assistant-menu"
        aria-haspopup="menu"
        aria-expanded={false}
        aria-controls="assistant-menu"
        title="Chọn trợ lý"
      >
        Trợ lý Luật Giao thông <ChevronDown aria-hidden="true" />
      </button>
    </header>
  );
}
