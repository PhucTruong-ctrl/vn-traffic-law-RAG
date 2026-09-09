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
  const resizeTextarea = (textarea: HTMLTextAreaElement) => {
    const transition = textarea.style.transition;
    textarea.style.transition = "none";
    textarea.style.height = "0px";
    const lineHeight = Number.parseFloat(getComputedStyle(textarea).lineHeight) || 23;
    const maxHeight = hero ? Number.POSITIVE_INFINITY : lineHeight * 8 + 24;
    const nextHeight = Math.max(lineHeight + 24, Math.min(textarea.scrollHeight, maxHeight));
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
    void textarea.offsetHeight;
    textarea.style.transition = transition;
  };
  useEffect(() => {
    if (textareaRef.current) resizeTextarea(textareaRef.current);
  }, [value, hero]);
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };
  return (
    <form
      onSubmit={onSubmit}
      className={hero ? "composer hero-composer" : "composer compact-composer"}
    >
      <label htmlFor={id}>Câu hỏi</label>
      <textarea
        ref={textareaRef}
        id={id}
        required
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          resizeTextarea(event.currentTarget);
        }}
        onKeyDown={onKeyDown}
        placeholder={hero ? "Bạn muốn hỏi điều gì?" : "Hỏi tiếp..."}
        rows={hero ? 2 : 1}
      />
      <div className="composer-actions">
        <span className="scope-chip">Luật giao thông</span>
        {loading ? (
          <button type="button" aria-label="Dừng tra cứu" onClick={onStop}>
            Dừng
          </button>
        ) : (
          <button type="submit" aria-label="Gửi" disabled={!value.trim()}>
            <SendIcon />
          </button>
        )}
      </div>
    </form>
  );
}
