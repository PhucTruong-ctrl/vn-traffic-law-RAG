import { ChevronDownIcon } from "./Icons";
type Theme = "auto" | "light" | "dark";
export default function AppHeader({
  theme,
  onTheme,
}: {
  theme: Theme;
  onTheme: (theme: Theme) => void;
}) {
  return (
    <header className="app-header">
      <button type="button" className="assistant-menu">
        Trợ lý Luật Giao thông <ChevronDownIcon />
      </button>
      <fieldset className="theme-picker">
        <legend>Giao diện</legend>
        {(
          [
            ["auto", "Tự động"],
            ["light", "Sáng"],
            ["dark", "Tối"],
          ] as const
        ).map(([value, label]) => (
          <label key={value}>
            <input
              type="radio"
              name="theme"
              value={value}
              checked={theme === value}
              onChange={() => onTheme(value)}
            />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
    </header>
  );
}
