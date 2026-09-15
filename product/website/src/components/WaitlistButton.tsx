import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { createPortal } from "react-dom";
import { productApiBaseUrl } from "../api/client";
import "./waitlist.css";

/**
 * The waitlist: a native form in a drawer, not an embedded Typeform.
 *
 * A DRAWER from the right rather than a page or a centred modal: the trigger
 * lives in the nav on every page, and the page the reader was convinced by
 * stays visible behind the form — a signup is a low-commitment aside, not a
 * destination. The element underneath is still a <dialog> opened with
 * showModal(), so the focus trap, the Escape key and the top layer come from
 * the platform; the drawer is only its costume.
 *
 * TWO PIECES, not one. WaitlistDrawer holds the form and owns its own
 * lifecycle; WaitlistButton wraps it with a trigger for the plain case.
 * They separate because of the mobile nav sheet: a drawer whose state lives
 * in its trigger dies with the menu that hosted the trigger — the sheet
 * closes, the button unmounts, and the form it just opened goes with it.
 * The sheet therefore renders its own trigger and mounts the drawer OUTSIDE
 * itself, handing it a way back to the menu.
 *
 * Submissions go to the API (POST /api/v1/waitlist), which records the row
 * and sends the welcome email for a first signup. The form treats a repeat
 * email as success, because the endpoint does — who is already on the list
 * is not the browser's business.
 *
 * PORTALLED INTO .gr-root, not document.body. Custom properties resolve
 * through the DOM tree even for a top-layer dialog, so this is what puts the
 * design system's tokens in scope — the drawer is set in gr-heading,
 * gr-label and gr-button like everything else, instead of a private copy of
 * the system in rem. (Same lesson as SectionFab.)
 */

const COMPANY_SIZES = [
  "1-10",
  "11-50",
  "51-200",
  "201-500",
  "501-1000",
  "1001-5000",
  "5001+",
] as const;

/** Matches the drawer's slide-out duration in waitlist.css. A timer rather
 *  than transitionend, which never fires under reduced motion. */
const CLOSE_MS = 240;

type Phase = "idle" | "submitting" | "done";

export const WaitlistDrawer = ({
  onExited,
  handoff,
}: {
  /** The exit has finished; the owner should unmount the drawer now. */
  onExited: () => void;
  /** Present when the drawer was opened from a panel already standing at
   *  the right edge (the mobile nav sheet). The drawer then skips its own
   *  slide-in and swaps content in place — to the reader the panel never
   *  left — and shows a back arrow whose openMenu brings the menu back the
   *  same way. */
  handoff?: { openMenu: () => void };
}) => {
  const [closing, setClosing] = useState(false);
  const [returning, setReturning] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);

  /* No JS scroll lock here: waitlist.css holds it via body:has(dialog[open]).
     An inline-style lock cannot be shared with the nav sheet — whichever
     panel unmounts second would restore a stale value and unlock the page
     under the one still open. */
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  /* Leaves the way it came: the closing class plays the slide-out, and the
     owner unmounts the drawer once it has left the screen. Cancel (Escape)
     is intercepted so even the platform's own close goes through the exit. */
  const close = () => {
    if (closing) return;
    setClosing(true);
    window.setTimeout(onExited, CLOSE_MS);
  };

  /* Back is not close: the panel stays, the form's content slides away, and
     the menu is standing underneath by the time the dialog leaves the top
     layer — the reverse of the swap that opened it. */
  const backToMenu = () => {
    if (closing) return;
    setReturning(true);
    handoff?.openMenu();
    close();
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (phase === "submitting") return;
    const form = new FormData(event.currentTarget);
    const body = {
      email: String(form.get("email") ?? "").trim(),
      companySize: String(form.get("companySize") ?? ""),
      monthlyTokenSpendUsd: String(
        form.get("monthlyTokenSpendUsd") ?? "",
      ).trim(),
      motivation: String(form.get("motivation") ?? "").trim(),
    };
    setPhase("submitting");
    setError(null);
    try {
      const response = await fetch(`${productApiBaseUrl}/api/v1/waitlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setEmail(body.email);
      setPhase("done");
    } catch {
      setPhase("idle");
      setError("That didn't go through. Please try again in a moment.");
    }
  };

  return createPortal(
    <dialog
      className={`gr-waitlist-drawer${closing ? " gr-waitlist-drawer--closing" : ""}${handoff ? " gr-waitlist-drawer--handoff" : ""}${returning ? " gr-waitlist-drawer--returning" : ""}`}
      ref={dialogRef}
      aria-label="Join the Gradiated waitlist"
      onKeyDown={(event) => event.stopPropagation()}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        /* The backdrop is part of the dialog's own box: a click whose
           target is the dialog element itself landed outside the
           drawer's content, which is a dismissal. */
        if (event.target === dialogRef.current) close();
      }}
    >
      <div className="gr-waitlist-body">
        {handoff ? (
          <button
            aria-label="Back to menu"
            className="gr-waitlist-back"
            type="button"
            onClick={backToMenu}
          >
            <svg
              aria-hidden
              fill="none"
              height="16"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              viewBox="0 0 24 24"
              width="16"
            >
              <path d="M19 12H5" />
              <path d="m12 19-7-7 7-7" />
            </svg>
            Menu
          </button>
        ) : null}
        {phase === "done" ? (
          <div className="gr-waitlist-done" role="status">
            <h2 className="gr-heading">You&rsquo;re on the list.</h2>
            <p className="gr-body gr-muted">
              Thanks — a confirmation is on its way to <strong>{email}</strong>.
              Your beta invitation will land at the same address.
            </p>
            <button
              className="gr-button gr-button--main gr-waitlist-submit"
              type="button"
              onClick={close}
            >
              Done
            </button>
          </div>
        ) : (
          <>
            <header className="gr-waitlist-head">
              <h2 className="gr-heading">Join the beta</h2>
              <p className="gr-body gr-muted">
                Tell us about your company, and we&rsquo;ll be in touch with
                early access details.
              </p>
            </header>

            <form className="gr-waitlist-form" onSubmit={submit}>
              <label>
                <span className="gr-label">
                  Work email (for beta invitation)
                </span>
                <input
                  autoFocus
                  name="email"
                  type="email"
                  required
                  maxLength={320}
                  placeholder="name@example.com"
                  autoComplete="email"
                />
              </label>

              <label>
                <span className="gr-label">How big is your company?</span>
                <select name="companySize" required defaultValue="">
                  <option value="" disabled>
                    Select company size
                  </option>
                  {COMPANY_SIZES.map((size) => (
                    <option key={size} value={size}>
                      {size} employees
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span className="gr-label">Estd monthly token spend (USD)</span>
                <input
                  name="monthlyTokenSpendUsd"
                  type="text"
                  inputMode="decimal"
                  required
                  maxLength={100}
                  placeholder="2,500"
                />
              </label>

              <label>
                <span className="gr-label">
                  What is prompting you to switch your inference to open-source
                  models?
                </span>
                <textarea
                  name="motivation"
                  required
                  maxLength={4000}
                  rows={3}
                />
              </label>

              {error ? (
                <p className="gr-body gr-waitlist-error" role="alert">
                  {error}
                </p>
              ) : null}

              <button
                className="gr-button gr-button--main gr-waitlist-submit"
                type="submit"
                disabled={phase === "submitting"}
              >
                {phase === "submitting" ? "Joining…" : "Join the waitlist"}
              </button>
            </form>
          </>
        )}
      </div>
    </dialog>,
    document.querySelector(".gr-root") ?? document.body,
  );
};

/** Trigger and drawer in one, for call sites that outlive the drawer. A
 *  trigger inside the mobile nav sheet must NOT use this — see the file
 *  comment — the sheet renders its own button and mounts the drawer
 *  outside itself. */
export const WaitlistButton = ({
  className,
  children = "Join the waitlist",
}: {
  className?: string;
  children?: ReactNode;
}) => {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button
        ref={triggerRef}
        className={`gr-waitlist-trigger ${className ?? ""}`}
        type="button"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        {children}
      </button>
      {open && (
        <WaitlistDrawer
          onExited={() => {
            setOpen(false);
            triggerRef.current?.focus();
          }}
        />
      )}
    </>
  );
};
