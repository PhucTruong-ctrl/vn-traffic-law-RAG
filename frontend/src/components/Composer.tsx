import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { Square, Send } from "lucide-react";
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
  const [resizing, setResizing] = useState(false);
  const resizePulseRef = useRef<number | null>(null);
  const resizeTextarea = useCallback(
    (textarea: HTMLTextAreaElement) => {
      textarea.style.transition = "none";
      textarea.style.height = "0px";
      const lineHeight = Number.parseFloat(getComputedStyle(textarea).lineHeight) || 23;
      const verticalPadding = hero ? 24 : 28;
      const maxHeight = hero ? Number.POSITIVE_INFINITY : lineHeight * 8 + verticalPadding;
      const nextHeight = Math.max(
        lineHeight + verticalPadding,
        Math.min(textarea.scrollHeight, maxHeight),
      );
      textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
      textarea.style.height = `${nextHeight}px`;
      if (hero || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      setResizing(false);
      void textarea.offsetHeight;
      setResizing(true);
      if (resizePulseRef.current !== null) window.clearTimeout(resizePulseRef.current);
      resizePulseRef.current = window.setTimeout(() => {
        setResizing(false);
        resizePulseRef.current = null;
      }, 220);
    },
    [hero],
  );
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (textareaRef.current) resizeTextarea(textareaRef.current);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [resizeTextarea]);
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };
  return (
    <form
      onSubmit={onSubmit}
      className={`${hero ? "composer hero-composer" : "composer compact-composer"}${
        resizing ? " is-resizing" : ""
      }`}
    >
      <label htmlFor={id}>Câu hỏi</label>
      <textarea
        ref={textareaRef}
        id={id}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          window.setTimeout(() => {
            if (textareaRef.current) resizeTextarea(textareaRef.current);
          }, 0);
        }}
        onKeyDown={onKeyDown}
        placeholder={hero ? "Bạn muốn hỏi điều gì?" : "Hỏi tiếp..."}
        rows={hero ? 2 : 1}
      />
      <div className="composer-actions">
        {loading ? (
          <button type="button" aria-label="Dừng tra cứu" title="Dừng tra cứu" onClick={onStop}>
            <Square size={17} fill="currentColor" aria-hidden="true" />
          </button>
        ) : (
          <button type="submit" aria-label="Gửi" title="Gửi" disabled={!value.trim()}>
            <Send size={17} aria-hidden="true" />
          </button>
        )}
      </div>
    </form>
  );
}
