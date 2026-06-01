import { ReactNode, useEffect, useRef } from "react";
import { createPortal } from "react-dom";

interface ModalShellProps {
  title: string;
  titleId: string;
  closeLabel: string;
  className?: string;
  children: ReactNode;
  footer: ReactNode;
  onClose(): void;
}

export function ModalShell({ title, titleId, closeLabel, className = "", children, footer, onClose }: ModalShellProps) {
  const modalRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }

      if (event.key === "Tab" && modalRef.current) {
        const focusable = Array.from(
          modalRef.current.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])'
          )
        );
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
        return;
      }

      if (event.key === "Enter" && modalRef.current && event.target instanceof HTMLElement) {
        const tagName = event.target.tagName.toLowerCase();
        const isEditable = event.target.isContentEditable || ["input", "select", "textarea"].includes(tagName);
        const defaultAction = modalRef.current.querySelector<HTMLButtonElement>("[data-default-action='true']:not(:disabled)");
        if (!isEditable && defaultAction) {
          event.preventDefault();
          defaultAction.click();
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    window.setTimeout(() => {
      const focusTarget = modalRef.current?.querySelector<HTMLElement>(
        "[autofocus], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex='-1'])"
      );
      focusTarget?.focus();
    }, 0);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, []);

  const modal = (
    <div className="modal-backdrop" role="presentation">
      <section ref={modalRef} className={`modal ${className}`.trim()} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <header className="modal-header">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label={`${closeLabel} (Esc)`} title="Esc">X</button>
        </header>
        <div className="modal-body">{children}</div>
        <footer className="modal-actions">{footer}</footer>
      </section>
    </div>
  );

  return createPortal(modal, document.body);
}
