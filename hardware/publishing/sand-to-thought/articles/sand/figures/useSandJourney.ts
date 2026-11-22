import { useEffect, useState } from "react";
import type { RefObject } from "react";

type Chapter = { id: string; label: string };
type HostRef = RefObject<HTMLElement | null>;

export const useSandAnimation = (hostRef: HostRef): void => {
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let cleanup = () => {};

    void import("./runtime/main.js").then(({ mountSandScenes }) => {
      if (disposed) return;

      cleanup = mountSandScenes(host);
      host.dataset.animationReady = "true";

      const target = document.getElementById(window.location.hash.slice(1));
      if (target && host.contains(target)) {
        target.scrollIntoView({ behavior: "instant", block: "start" });
      }
    });

    return () => {
      disposed = true;
      cleanup();
    };
  }, [hostRef]);
};

export const useSandSubsections = (
  hostRef: HostRef,
  chapters: readonly Chapter[],
): Record<string, Chapter[]> => {
  const [subsections, setSubsections] = useState<Record<string, Chapter[]>>({});

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const sections: Record<string, Chapter[]> = {};
    let chapter = "";

    for (const scene of host.querySelectorAll<HTMLElement>(".scene-text")) {
      if (chapters.some(({ id }) => id === scene.id)) chapter = scene.id;
      if (!chapter) continue;

      const heading = scene.querySelector("h3");
      if (heading) {
        (sections[chapter] ??= []).push({
          id: scene.id,
          label: heading.textContent?.trim() ?? "",
        });
      }
    }

    setSubsections(sections);
  }, [hostRef, chapters]);

  return subsections;
};

export const useActiveChapter = (
  hostRef: HostRef,
  chapters: readonly Chapter[],
): string => {
  const [active, setActive] = useState(chapters[0].id);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let frame = 0;

    const measure = () => {
      frame = 0;
      const line = window.innerHeight * (window.innerWidth <= 640 ? 0.72 : 0.5);
      let current = chapters[0].id;

      for (const { id } of chapters) {
        const target = host.querySelector<HTMLElement>(`#${id}`);
        if (target && target.getBoundingClientRect().top <= line + 2) {
          current = id;
        }
      }

      setActive(current);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };

    measure();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, [hostRef, chapters]);

  return active;
};
