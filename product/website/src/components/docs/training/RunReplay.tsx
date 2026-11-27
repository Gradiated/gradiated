import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";

import { useNearViewport } from "./hooks";

type Segment = [string, string];
type Frame = {
  label: string;
  step: number;
  wide: number[];
  narrow: number[];
};
type Recording = {
  source: string;
  rows: Segment[][];
  size: [number, number];
  frames: Frame[];
  interrupt_after: number;
  interrupt: Frame[];
};

type Entry = { kind: "frame"; frame: Frame } | { kind: "summary" };

const COMMAND =
  "grad train --dataset support-prod --name support-sft --recipe sft --model test/tiny-qwen3 --batch-size 1 --epochs 3 --max-cost-usd 0.05 --wait";

/* What train.rs prints on the normal screen once the view closes, for this
   run: the dataset line before it opens, then report_finished. */
const SUMMARY = (interrupted: boolean): string[] => [
  "✓ Dataset support-prod: 400 records (version 1)",
  `✓ Trained test/tiny-qwen3 sft in ${interrupted ? "41s" : "11s"} (~15.9k tokens, $0.02)`,
  "",
  "  Eval report:",
  "    metric name       : eval_loss",
  "    selected step     : 1,062",
  "    best step         : 1,062",
  "    final step        : 1,062",
  "    train records     : 354",
  "    eval records      : 46",
  "    eval loss         : 0.6059",
  "    train examples    : 354",
  "    eval examples     : 46",
  "    reference backend : true",
  "    ! Reference test backend: the base model was not trained; the artifact is not deployable.",
  "",
  "✓ Exported artifact support-sft@2026-11-27-1",
  "  This is a reference-backend test artifact; it cannot be deployed.",
];

const CHAPTERS: Record<string, string> = {
  queued: "Waiting for a GPU",
  training: "Training",
  "connection lost": "Interrupted",
  requeued: "Interrupted",
  resuming: "Resuming from checkpoint",
  completed: "Completed",
};

const delayFor = (entry: Entry): number => {
  if (entry.kind === "summary") return 0;

  switch (entry.frame.label) {
    case "queued":
      return 650;
    case "training":
      return 230;
    case "completed":
      return 1800;
    default:
      return 1100;
  }
};

const styleClass = (code: string): string | undefined => {
  if (code === "-") return undefined;

  const classes: string[] = [];
  if (code[0] !== "-") classes.push(`gr-tty-${code[0]}`);
  for (const flag of code.slice(1)) classes.push(`gr-tty-${flag}`);
  return classes.join(" ");
};

/* Braille plots and block sparklines come from fallback fonts whose glyphs
   are not one column wide; pin every non-ASCII glyph to a single cell so the
   panel borders stay straight. */
const cells = (text: string): ReactNode[] =>
  Array.from(text.matchAll(/[\x00-\x7f]+|[^\x00-\x7f]/gu), ([run], i) =>
    run.charCodeAt(0) > 0x7f ? (
      <span className="gr-tty-cell" key={i}>
        {run}
      </span>
    ) : (
      run
    ),
  );

const Rows = ({
  ids,
  rows,
}: {
  ids: number[];
  rows: Segment[][];
}): ReactElement => (
  <>
    {ids.map((id, y) => (
      <span className="gr-tty-row" key={y}>
        {rows[id].map(([text, code], x) => (
          <span className={styleClass(code)} key={x}>
            {cells(text)}
          </span>
        ))}
        {"\n"}
      </span>
    ))}
  </>
);

export const RunReplay = (): ReactElement => {
  const [recording, setRecording] = useState<Recording | null>(null);
  const [failed, setFailed] = useState(false);
  const [interrupt, setInterrupt] = useState(true);
  const [index, setIndex] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [narrow, setNarrow] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const near = useNearViewport(box);

  useEffect(() => {
    if (!near || recording) return;

    import("./run-replay.json")
      .then((module) => setRecording(module.default as unknown as Recording))
      .catch(() => setFailed(true));
  }, [near, recording]);

  useEffect(() => {
    const element = box.current;
    if (!element) return;

    const observer = new ResizeObserver(([entry]) => {
      setNarrow(entry.contentRect.width < 620);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const timeline = useMemo<Entry[]>(() => {
    if (!recording) return [];

    const frames = interrupt
      ? [
          ...recording.frames.slice(0, recording.interrupt_after),
          ...recording.interrupt,
        ]
      : recording.frames;
    return [
      ...frames.map((frame) => ({ kind: "frame" as const, frame })),
      { kind: "summary" as const },
    ];
  }, [recording, interrupt]);

  /* Open on the mid-run view: the most informative single frame. */
  const restingIndex = useMemo(
    () =>
      Math.max(
        0,
        timeline.findIndex(
          (entry) => entry.kind === "frame" && entry.frame.step >= 640,
        ),
      ),
    [timeline],
  );
  const current = Math.min(index ?? restingIndex, timeline.length - 1);
  const entry = timeline[current];

  useEffect(() => {
    if (!playing || !entry) return;

    if (current >= timeline.length - 1) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(
      () => setIndex(current + 1),
      delayFor(entry),
    );
    return () => window.clearTimeout(timer);
  }, [playing, current, entry, timeline.length]);

  const play = () => {
    if (current >= timeline.length - 1 || index === null) setIndex(0);
    setPlaying(true);
  };

  const step = (delta: number) => {
    setPlaying(false);
    setIndex(Math.max(0, Math.min(timeline.length - 1, current + delta)));
  };

  const chapter =
    entry?.kind === "summary"
      ? "After the view closes"
      : entry
        ? (CHAPTERS[entry.frame.label] ?? entry.frame.label)
        : "Loading the recording";

  const marks = timeline
    .map((item, i) => ({ item, i }))
    .filter(
      ({ item, i }) =>
        i === 0 ||
        item.kind === "summary" ||
        (item.kind === "frame" &&
          timeline[i - 1].kind === "frame" &&
          CHAPTERS[item.frame.label] !==
            CHAPTERS[(timeline[i - 1] as { frame: Frame }).frame.label]),
    );

  return (
    <figure className="gr-dx gr-dx-replay" ref={box}>
      <div className="gr-dx-replay-cmd">
        <span aria-hidden="true">$</span>
        <code>{COMMAND}</code>
      </div>

      <div
        aria-label={`grad train full-screen view, ${chapter}`}
        className="gr-dx-replay-screen"
        data-narrow={narrow ? "true" : undefined}
        role="img"
      >
        {failed ? (
          <p className="gr-dx-replay-empty">
            The recording didn't load. The same frames are in grad's
            cli/tests/snapshots/tui/.
          </p>
        ) : !entry ? (
          <p className="gr-dx-replay-empty">Loading the recording…</p>
        ) : entry.kind === "summary" ? (
          <pre className="gr-tty">{SUMMARY(interrupt).join("\n")}</pre>
        ) : (
          <pre className="gr-tty">
            <Rows
              ids={narrow ? entry.frame.narrow : entry.frame.wide}
              rows={recording?.rows ?? []}
            />
          </pre>
        )}
      </div>

      <div className="gr-dx-replay-controls">
        <button
          aria-label={playing ? "Pause" : "Play the recording"}
          className="gr-dx-button"
          disabled={!recording}
          onClick={() => (playing ? setPlaying(false) : play())}
          type="button"
        >
          {playing
            ? "Pause"
            : current >= timeline.length - 1
              ? "Replay"
              : "Play"}
        </button>
        <button
          aria-label="Previous frame"
          className="gr-dx-button gr-dx-button--quiet"
          disabled={!recording || current === 0}
          onClick={() => step(-1)}
          type="button"
        >
          ←
        </button>
        <button
          aria-label="Next frame"
          className="gr-dx-button gr-dx-button--quiet"
          disabled={!recording || current >= timeline.length - 1}
          onClick={() => step(1)}
          type="button"
        >
          →
        </button>
        <div className="gr-dx-replay-scrub">
          <input
            aria-label="Position in the recording"
            aria-valuetext={chapter}
            disabled={!recording}
            max={Math.max(0, timeline.length - 1)}
            min={0}
            onChange={(event) => {
              setPlaying(false);
              setIndex(Number(event.target.value));
            }}
            type="range"
            value={current}
          />
          <div aria-hidden="true" className="gr-dx-replay-marks">
            {marks.map(({ item, i }) => (
              <span
                key={i}
                style={{
                  left: `${(i / Math.max(1, timeline.length - 1)) * 100}%`,
                }}
                title={
                  item.kind === "summary"
                    ? "Summary"
                    : CHAPTERS[item.frame.label]
                }
              />
            ))}
          </div>
        </div>
        <label className="gr-dx-check">
          <input
            checked={interrupt}
            onChange={(event) => {
              setInterrupt(event.target.checked);
              setIndex(null);
              setPlaying(false);
            }}
            type="checkbox"
          />
          Lose the worker at step 652
        </label>
      </div>

      <figcaption className="gr-dx-caption">
        <strong>{chapter}.</strong> Drawn by grad's real terminal renderer from
        a recorded run on the reference test worker (a tiny test model, so the
        loss barely moves and throughput is unrealistically high). The
        interruption is injected the way the CLI's own test does it: the run
        resumes from its last checkpoint at step 640 and replays the steps after
        it.
      </figcaption>
    </figure>
  );
};

export default RunReplay;
