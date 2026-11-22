export const SAND_PROGRESS = (function () {
  const progressAt = (bounds, y) => {
    if (!bounds.length || y <= bounds[0].center) return 0;

    // Preserve the original centre-to-centre choreography of the protected artwork.
    for (let i = 0; i < Math.min(3, bounds.length - 1); i++) {
      if (y <= bounds[i + 1].center) {
        const span = bounds[i + 1].center - bounds[i].center;
        return i + Math.max(0, Math.min(1, (y - bounds[i].center) / span));
      }
    }

    for (let i = 3; i < bounds.length; i++) {
      const current = bounds[i],
        next = bounds[i + 1];
      if (y <= current.end || !next) return i;
      if (y < next.start) {
        const span = next.start - current.end;
        return i + Math.max(0, Math.min(1, (y - current.end) / span));
      }
    }

    return bounds.length - 1;
  };

  return { progressAt };
})();
