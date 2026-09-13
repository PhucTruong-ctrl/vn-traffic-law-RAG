"use client";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useEffect, useRef } from "react";
type ModalProps = {
  open: boolean;
  onClose: () => void;
  label: string;
  className?: string;
  children: React.ReactNode;
};

export default function Modal({ open, onClose, label, className = "", children }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    root.style.overflow = "hidden";
    const previousFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusCloseButton = () => closeButtonRef.current?.focus();
    // The dialog and its close button mount in the same render as `open`; defer
    // focus until the browser has committed that DOM, including conditional
    // dialog content such as the PDF error/missing-bbox state.
    const frame = requestAnimationFrame(focusCloseButton);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const controls = [
        ...dialogRef.current.querySelectorAll<HTMLElement>(
          'button, a[href], input, textarea, select, [tabindex]:not([tabindex="-1"])',
        ),
      ].filter((control) => !control.hasAttribute("disabled"));
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeyDown);
      root.style.overflow = previousOverflow;
      previousFocus?.focus({ preventScroll: true });
    };
  }, [open, onClose]);

  if (!open || typeof document === "undefined") return null;
  return createPortal(
    <div
      className="modal-backdrop"
      role="presentation"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className={`modal ${className}`}
        role="dialog"
        aria-modal="true"
        aria-label={label}
      >
        <button
          ref={closeButtonRef}
          type="button"
          className="modal__close"
          aria-label={`Đóng ${label}`}
          title={`Đóng ${label}`}
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </button>
        {children}
      </div>
    </div>,
    document.body,
  );
}
