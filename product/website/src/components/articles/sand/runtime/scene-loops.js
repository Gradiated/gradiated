export const syncSceneLoops = (
  loops,
  progress,
  inTransition,
  reduced,
  suspended,
) => {
  for (const loop of loops) {
    const active =
      !reduced && !inTransition && Math.round(progress) === loop.scene;

    if (active && loop.tween.paused()) {
      if (suspended.has(loop.tween)) loop.tween.resume();
      else loop.tween.restart(true);
    } else if (!active && (!loop.tween.paused() || suspended.has(loop.tween))) {
      loop.tween.pause();
      if (loop.reset) loop.reset();
      else loop.tween.pause(0);
    }
  }

  suspended.clear();
};
