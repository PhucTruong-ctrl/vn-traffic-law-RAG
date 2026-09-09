import { FormEvent, KeyboardEvent } from "react";
import { SendIcon } from "./Icons";

type ComposerProps = {
  id: string;
  value: string;
  loading?: boolean;
  hero?: boolean;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};
export default function Composer({
  id,
  value,
  loading = false,
  hero = false,
  onChange,
  onSubmit,
}: ComposerProps) {
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };
  return (
    <form
      onSubmit={onSubmit}
      className={hero ? "composer hero-composer" : "composer"}
    >
      <label htmlFor={id}>Câu hỏi</label>
      <textarea
        id={id}
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={hero ? "Bạn muốn hỏi điều gì?" : "Hỏi tiếp..."}
        rows={hero ? 2 : 1}
      />
      <div className="composer-actions">
        <span className="scope-chip">Luật giao thông</span>
        <button
          type="submit"
          aria-label={loading ? "Đang tra cứu..." : "Gửi"}
          disabled={Boolean(loading || !value.trim())}
        >
          <SendIcon />
        </button>
      </div>
    </form>
  );
}
