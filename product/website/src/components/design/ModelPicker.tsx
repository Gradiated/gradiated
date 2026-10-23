import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

/**
 * The open-model picker that sits beside the endpoint field in both
 * machines — sized to the field's own height so the control row reads as
 * one instrument. One list, shared, so the two folds cannot disagree
 * about the catalogue.
 */

export const OPEN_MODELS = [
  { name: "Llama 4", src: "/assets/models/meta-color.svg" },
  { name: "Qwen 3", src: "/assets/models/qwen-color.svg" },
  { name: "DeepSeek V3", src: "/assets/models/deepseek-color.svg" },
] as const;

export const ModelPicker = ({
  onChange,
  value,
}: {
  onChange: (index: number) => void;
  value: number;
}): ReactElement => {
  const [open, setOpen] = useState(false);
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!hostRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  const current = OPEN_MODELS[value];
  return (
    <div
      className={`gr-mpick${open ? " gr-mpick--open" : ""}`}
      ref={hostRef}
    >
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        className="gr-mpick-btn"
        onClick={() => setOpen((o) => !o)}
        type="button"
      >
        <img alt="" src={current.src} />
        <span>{current.name}</span>
        <span aria-hidden className="gr-mpick-chev">
          &#9662;
        </span>
      </button>
      <div className="gr-mpick-menu" role="listbox">
        {OPEN_MODELS.map((item, index) => (
          <button
            aria-selected={index === value}
            className={`gr-mpick-item${index === value ? " gr-mpick-item--on" : ""}`}
            key={item.name}
            onClick={() => {
              onChange(index);
              setOpen(false);
            }}
            role="option"
            type="button"
          >
            <img alt="" src={item.src} />
            {item.name}
          </button>
        ))}
      </div>
    </div>
  );
};
