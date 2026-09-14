import { useEffect, useRef, useState } from "react";
import { SoundOffIcon, SoundOnIcon } from "./icons";
import type { CSSProperties, ReactElement } from "react";

/**
 * A vertical reel: one chapter at a time, advancing on its own, with the
 * caption changing as it goes.
 *
 * The progress bar is segmented — one segment per chapter, the current one
 * filling — which is the convention people already know from stories. It is
 * also the navigation: a segment is a button, so the reel can be read in any
 * order rather than only waited through.
 *
 * TIMING COMES FROM THE VIDEO where there is one. `duration` is the fallback
 * for a chapter with no media yet, and the interval is only used then — a
 * timer running alongside a video is a timer that will disagree with it.
 */

export type Chapter = {
  body: string;
  title: string;
  /** Basename in /brand/reel/. Falls back to a placeholder when absent. */
  video?: string;
};

/** How long a chapter with no video holds, in ms. */
const FALLBACK_MS = 6000;

/** How often the fill is repainted while a chapter plays. */
const TICK_MS = 50;

export const StoryReel = ({
  chapters,
  playbackRate = 1,
}: {
  chapters: Chapter[];
  playbackRate?: number;
}): ReactElement => {
  const [index, setIndex] = useState(0);
  const [progress, setProgress] = useState(0);
  /* Starts silent, and has to: a browser refuses to autoplay a reel with
     sound, and the refusal takes the picture down with it. Sound is something
     the reader turns on. */
  const [soundOn, setSoundOn] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  /* Read by the play effect without being a dependency of it — the effect
     rewinds to zero, so listing soundOn there would restart the chapter every
     time the reader touched the button. */
  const soundOnRef = useRef(soundOn);
  soundOnRef.current = soundOn;

  const chapter = chapters[index];
  const advance = () => setIndex((i) => (i + 1) % chapters.length);

  /* The preference outlives the element. Each chapter mounts its own <video>
     (keyed on the file), so without this the reel would fall back to silent
     every time it advanced. */
  useEffect(() => {
    const video = videoRef.current;
    if (video) video.muted = !soundOn;
  }, [soundOn, index]);

  /* One effect per chapter, so switching chapters tears down the previous
     one's timer or listeners rather than leaving them running. */
  useEffect(() => {
    setProgress(0);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduced.matches) return;

    const video = videoRef.current;
    if (video) {
      const onTime = () => {
        if (video.duration) setProgress(video.currentTime / video.duration);
      };
      video.playbackRate = playbackRate;
      video.currentTime = 0;
      video.muted = !soundOnRef.current;
      void video.play().catch(() => {});
      video.addEventListener("timeupdate", onTime);
      video.addEventListener("ended", advance);
      return () => {
        video.removeEventListener("timeupdate", onTime);
        video.removeEventListener("ended", advance);
      };
    }

    const started = performance.now();
    const timer = setInterval(() => {
      const done = (performance.now() - started) / FALLBACK_MS;
      if (done >= 1) advance();
      else setProgress(done);
    }, TICK_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, chapters.length, playbackRate]);

  return (
    <div className="gr-reel">
      <div className="gr-reel-stage">
        {chapter.video ? (
          <video
            key={chapter.video}
            muted
            playsInline
            poster={`/brand/reel/${chapter.video}-poster.jpg`}
            preload="metadata"
            ref={videoRef}
          >
            <source src={`/brand/reel/${chapter.video}.webm`} type="video/webm" />
            <source src={`/brand/reel/${chapter.video}.mp4`} type="video/mp4" />
          </video>
        ) : null}

        {/* Only where there is something to hear. The placeholder chapters
            have no audio to turn on, and a dead control is worse than none. */}
        {chapter.video ? (
          <button
            aria-label={soundOn ? "Mute" : "Unmute"}
            aria-pressed={soundOn}
            className="gr-reel-sound"
            onClick={() => setSoundOn((on) => !on)}
            type="button"
          >
            {soundOn ? <SoundOnIcon /> : <SoundOffIcon />}
          </button>
        ) : null}

        {!chapter.video ? (
          /* PLACEHOLDER — the reel's footage. The chapter still times out and
             advances, so the sequence can be judged before the film exists. */
          <div className="gr-placeholder">Reel {index + 1}</div>
        ) : null}
      </div>

      <div aria-label="Chapters" className="gr-reel-progress" role="tablist">
        {chapters.map((entry, i) => (
          <button
            aria-selected={i === index}
            className="gr-reel-segment"
            key={entry.title}
            onClick={() => setIndex(i)}
            role="tab"
            style={
              {
                "--fill": i < index ? 1 : i === index ? progress : 0,
              } as CSSProperties
            }
            type="button"
          >
            <span className="gr-visually-hidden">{entry.title}</span>
          </button>
        ))}
      </div>

      <div className="gr-reel-caption">
        <h3 className="gr-heading">{chapter.title}</h3>
        <p className="gr-body gr-muted">{chapter.body}</p>
      </div>
    </div>
  );
};
