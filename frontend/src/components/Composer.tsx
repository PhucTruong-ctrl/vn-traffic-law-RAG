import { useEffect, useRef } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { SendIcon } from "./Icons";

type ComposerProps = {
  id: string;
  value: string;
  loading?: boolean;
  hero?: boolean;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onStop?: () => void;
};
export default function Composer({
  id,
  value,
  loading = false,
  hero = false,
  onChange,
  onSubmit,
  onStop,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const resizeTextarea = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  };
  useEffect(resizeTextarea, [value]);
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
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
        ref={textareaRef}
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
        {loading ? (
          <button
            type="button"
            aria-label="Dừng tra cứu"
            onClick={onStop}
          >
            Dừng
          </button>
        ) : (
          <button
            type="submit"
            aria-label="Gửi"
            disabled={!value.trim()}
          >
            <SendIcon />
          </button>
        )}
      </div>
    </form>
  );
}
