import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { selectScrollScene } from "./scrollScene";

export const useActiveScene = (
  host: RefObject<HTMLElement | null>,
  sceneCount: number,
) => {
  const [{ active, zoom }, setSelection] = useState<{
    active: number;
    zoom: "instant" | "smooth";
    changedAt: number | null;
  }>({ active: 0, zoom: "instant", changedAt: null });
  const activeScene = useRef(active);
  const navigation = useRef<HTMLElement | null>(null);
  const pinned = useRef<HTMLElement | null>(null);

  useLayoutEffect(() => {
    activeScene.current = active;
    const element = host.current;
    const stage = element?.querySelector<HTMLElement>(".fpga-stage");
    if (!element || !stage) return;

    element.style.setProperty(
      "--fpga-stage-height",
      `${Math.ceil(stage.getBoundingClientRect().height)}px`,
    );
    stage.scrollTop = 0;
    stage.scrollLeft = 0;
    const viewport = stage.querySelector(".fpga-diagram-viewport");
    if (viewport) {
      viewport.scrollTop = 0;
      viewport.scrollLeft = 0;
    }

    if (navigation.current) {
      navigation.current.scrollIntoView({
        block: "start",
        behavior: "instant",
      });
      navigation.current = null;
    }
  }, [active, host]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;

    const body = element.querySelector(".fpga-body");
    const stage = element.querySelector<HTMLElement>(".fpga-stage");
    if (!body || !stage) return;

    const sections = [
      ...element.querySelectorAll<HTMLElement>("[data-fpga-scene]"),
    ];
    let frame = 0;
    let disposed = false;
    const select = (index: number) => {
      const now = performance.now();
      setSelection((previous) => {
        if (index === previous.active) return previous;

        const interrupted =
          previous.changedAt !== null && now - previous.changedAt < 650;
        return {
          active: index,
          zoom:
            Math.abs(index - previous.active) > 1 || interrupted
              ? "instant"
              : "smooth",
          changedAt: now,
        };
      });
    };
    const measure = () => {
      frame = 0;
      // Keep chapter jumps selected while fonts and figure layouts settle.
      if (navigation.current || pinned.current) return;

      const stacked = getComputedStyle(body).display === "block";
      const line = stacked
        ? Math.min(
            window.innerHeight - 16,
            stage.getBoundingClientRect().bottom + 32,
          )
        : window.innerHeight * 0.42;
      const positions = sections.map((section) => ({
        index: Number(section.dataset.fpgaScene),
        top: section.getBoundingClientRect().top,
      }));

      select(selectScrollScene(positions, line, activeScene.current));
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    const navigate = () => {
      pinned.current = null;
      const id = decodeURIComponent(window.location.hash.slice(1));
      const target = document.getElementById(id);
      const targetScene = target?.closest<HTMLElement>(".fpga-scene");
      if (target && targetScene && element.contains(target)) {
        pinned.current = target;
        const index = targetScene.dataset.fpgaScene;
        if (index !== undefined && Number(index) !== activeScene.current) {
          navigation.current = target;
          select(Number(index));
        } else {
          target.scrollIntoView({ block: "start", behavior: "instant" });
        }
      }

      schedule();
    };
    const resize = new ResizeObserver(() => {
      if (stage) {
        element.style.setProperty(
          "--fpga-stage-height",
          `${Math.ceil(stage.getBoundingClientRect().height)}px`,
        );
      }

      if (pinned.current && !navigation.current) {
        pinned.current.scrollIntoView({ block: "start", behavior: "instant" });
      }

      schedule();
    });
    const release = () => {
      pinned.current = null;
      schedule();
    };
    const keyScroll = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest("input, textarea, select, button, [contenteditable]")
      )
        return;
      if (
        [
          "ArrowDown",
          "ArrowUp",
          "PageDown",
          "PageUp",
          "Home",
          "End",
          " ",
        ].includes(event.key)
      )
        release();
    };
    const pointerScroll = (event: PointerEvent) => {
      if (event.target instanceof Node && !stage.contains(event.target))
        release();
    };
    const prose = element.querySelector(".fpga-prose");
    if (prose) resize.observe(prose);
    if (stage) resize.observe(stage);

    measure();
    navigate();
    void document.fonts.ready.then(() => {
      if (!disposed) navigate();
    });
    window.addEventListener("wheel", release, { passive: true });
    window.addEventListener("touchmove", release, { passive: true });
    window.addEventListener("keydown", keyScroll);
    window.addEventListener("pointerdown", pointerScroll);
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    window.addEventListener("hashchange", navigate);

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resize.disconnect();
      window.removeEventListener("wheel", release);
      window.removeEventListener("touchmove", release);
      window.removeEventListener("keydown", keyScroll);
      window.removeEventListener("pointerdown", pointerScroll);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("hashchange", navigate);
    };
  }, [host, sceneCount]);

  return { active, zoom };
};

export const useClock = (capture: () => void, enabled = true) => {
  const stage = useRef<HTMLDivElement>(null);
  const callback = useRef(capture);
  callback.current = capture;
  const [running, setRunning] = useState(false);
  const [visible, setVisible] = useState(false);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener("change", update);

    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const element = stage.current;
    if (!element) return;

    let intersecting = false;
    const update = () => setVisible(intersecting && !document.hidden);
    const observer = new IntersectionObserver(([entry]) => {
      intersecting = entry.isIntersecting;
      update();
    });
    observer.observe(element);
    document.addEventListener("visibilitychange", update);

    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
    };
  }, []);

  useEffect(() => {
    if (!enabled || reduced) setRunning(false);
    if (!running || !enabled || !visible || reduced) return;

    const timer = window.setInterval(() => callback.current(), 1300);

    return () => window.clearInterval(timer);
  }, [running, enabled, visible, reduced]);

  return { stage, running, setRunning, reduced };
};
