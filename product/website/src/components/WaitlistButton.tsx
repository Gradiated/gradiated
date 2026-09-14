import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import "./waitlist.css";

const WAITLIST_URL = "https://form.typeform.com/to/pU8EArMC";

export const WaitlistButton = ({
  className,
  children = "Join the waitlist",
}: {
  className?: string;
  children?: ReactNode;
}) => {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      triggerRef.current?.focus();
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        className={`waitlist-trigger ${className ?? ""}`}
        type="button"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        {children}
      </button>
      {open &&
        createPortal(
          <dialog
            className="waitlist-modal"
            ref={dialogRef}
            aria-label="Join the Gradiated waitlist"
            onKeyDown={(event) => event.stopPropagation()}
            onCancel={() => setOpen(false)}
            onClose={() => setOpen(false)}
          >
            <div className="waitlist-modal-header">
              <span>Join the waitlist</span>
              <a href={WAITLIST_URL} target="_blank" rel="noreferrer">
                Open form in a new tab
              </a>
              <button type="button" autoFocus onClick={() => setOpen(false)}>
                Close <span aria-hidden="true">×</span>
              </button>
            </div>
            <iframe
              src={WAITLIST_URL}
              title="Gradiated waitlist form"
              allow="camera; microphone; autoplay; encrypted-media; fullscreen"
            />
          </dialog>,
          document.body,
        )}
    </>
  );
};
