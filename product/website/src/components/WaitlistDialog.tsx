import { useEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

type WaitlistDialogProps = {
  open: boolean;
  onClose: () => void;
};

const questions = ["Cost", "Quality", "Latency", "Configurability"];
const identities = [
  "Developer",
  "Researcher",
  "Founder",
  "Infrastructure team",
  "Other",
];

const waitlistSchema = z.object({
  identity: z.string().min(1),
  email: z.string().email(),
});

type WaitlistFormValues = z.infer<typeof waitlistSchema>;

export const WaitlistDialog = ({
  open,
  onClose,
}: WaitlistDialogProps): ReactElement => {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [step, setStep] = useState<1 | 2>(1);
  const [selectedQuestions, setSelectedQuestions] = useState<string[]>([]);
  const {
    formState: { errors, isValid },
    handleSubmit,
    register,
    reset,
    setValue,
    watch,
  } = useForm<WaitlistFormValues>({
    defaultValues: { identity: "", email: "" },
    mode: "onChange",
    resolver: zodResolver(waitlistSchema),
  });
  const identity = watch("identity");
  const email = watch("email");

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const close = (): void => {
    dialogRef.current?.close();
    onClose();
    setStep(1);
    setSelectedQuestions([]);
    reset();
  };

  const toggleQuestion = (question: string): void => {
    setSelectedQuestions((current) =>
      current.includes(question)
        ? current.filter((item) => item !== question)
        : [...current, question],
    );
  };

  const submit = (data: WaitlistFormValues): void => {
    const body = `Questioning: ${selectedQuestions.join(", ")}\nWho is asking: ${data.identity}\nEmail: ${data.email}`;
    window.location.href = `mailto:team@gradiated.com?subject=Waitlist&body=${encodeURIComponent(body)}`;
  };

  const canSubmit = Boolean(identity && isValid && selectedQuestions.length);

  return (
    <dialog
      ref={dialogRef}
      className="waitlist-dialog"
      aria-labelledby="waitlist-question"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <form className="waitlist-inquiry" onSubmit={handleSubmit(submit)}>
        <button
          className="waitlist-close"
          type="button"
          aria-label="Close waitlist inquiry"
          onClick={close}
        >
          Close ×
        </button>
        <div className="waitlist-progress" aria-hidden="true">
          <i style={{ width: step === 1 ? "50%" : "100%" }} />
        </div>

        <section className={`waitlist-step${step === 1 ? " is-active" : ""}`}>
          <p className="waitlist-count">Question 01 / 02</p>
          <h2 id="waitlist-question">
            Which inference trade-offs matter to you?
          </h2>
          <p className="waitlist-guidance">Select one or more.</p>
          <div className="waitlist-options" data-options="question">
            {questions.map((question) => (
              <button
                key={question}
                type="button"
                aria-pressed={selectedQuestions.includes(question)}
                onClick={() => toggleQuestion(question)}
              >
                {question}
              </button>
            ))}
          </div>
          <button
            className="waitlist-next"
            type="button"
            disabled={!selectedQuestions.length}
            onClick={() => setStep(2)}
          >
            Continue →
          </button>
        </section>

        <section className={`waitlist-step${step === 2 ? " is-active" : ""}`}>
          <p className="waitlist-count">Question 02 / 02</p>
          <h2>Which best describes you?</h2>
          <p className="waitlist-guidance">Choose the closest fit.</p>
          <div className="waitlist-options" data-options="identity">
            {identities.map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={identity === value}
                onClick={() =>
                  setValue("identity", value, { shouldValidate: true })
                }
              >
                {value}
              </button>
            ))}
          </div>
          <label className="waitlist-email">
            Where should we continue the conversation?
            <span>
              <input
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                required
                {...register("email")}
              />
              <i className="waitlist-email-error" aria-live="polite">
                {errors.email?.message ?? ""}
              </i>
            </span>
          </label>
          <div className="waitlist-actions">
            <button
              className="waitlist-back"
              type="button"
              onClick={() => setStep(1)}
            >
              ← Back
            </button>
            <button
              className="waitlist-submit"
              type="submit"
              disabled={!canSubmit}
            >
              Join waitlist →
            </button>
          </div>
        </section>
        <a
          className="waitlist-skip"
          href="mailto:team@gradiated.com?subject=Waitlist"
        >
          Skip the questions — email us directly
        </a>
      </form>
    </dialog>
  );
};

export type WaitlistLinkProps = {
  children: ReactNode;
  className?: string;
  onOpen: () => void;
};

export const WaitlistLink = ({
  children,
  className,
  onOpen,
}: WaitlistLinkProps): ReactElement => (
  <a
    className={className}
    href="mailto:team@gradiated.com?subject=Waitlist"
    onClick={(event) => {
      event.preventDefault();
      onOpen();
    }}
  >
    {children}
  </a>
);
