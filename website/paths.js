(() => {
  const canvas = document.querySelector('.path-field');
  if (!canvas || matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const ctx = canvas.getContext('2d');
  const trails = [];
  let pointer = null;
  let lastPathOrigin = null;
  let lastSpawn = 0;
  let shouldSpawn = false;
  let frame;
  let pageHeight = 0;
  const spawnEvery = 60;

  function resize() {
    const scale = Math.min(devicePixelRatio || 1, 2);
    pageHeight = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, innerHeight);
    canvas.width = innerWidth * scale;
    canvas.height = pageHeight * scale;
    canvas.style.width = `${innerWidth}px`;
    canvas.style.height = `${pageHeight}px`;
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
  }

  function grow(x, y, angle, depth, length, seed) {
    const points = [{ x, y }];
    const steps = 6 + Math.floor(seed * 3);
    for (let i = 1; i <= steps; i++) {
      const progress = i / steps;
      if (i % 2 === 0) {
        angle += (Math.random() - 0.5) * 0.72;
        angle = Math.round(angle / (Math.PI / 2)) * (Math.PI / 2);
      }
      const step = (length / steps) * (0.72 + progress * 0.46);
      const previous = points[i - 1];
      points.push({ x: previous.x + Math.cos(angle) * step, y: previous.y + Math.sin(angle) * step });
    }
    trails.push({ points, born: performance.now(), duration: 2150 + depth * 150, depth, source: { x, y } });
    if (depth > 0) {
      const fork = points[Math.max(3, Math.floor(steps * (0.48 + seed * 0.22)))];
      const branchAngle = Math.round((angle + (seed > .5 ? Math.PI / 2 : -Math.PI / 2)) / (Math.PI / 2)) * (Math.PI / 2);
      grow(fork.x, fork.y, branchAngle, depth - 1, length * .57, Math.random());
    }
  }

  function spawn() {
    if (!pointer) return;
    const count = 1;
    for (let i = 0; i < count; i++) {
      const direction = Math.random() > .5 ? 0 : Math.PI;
      const exploratory = pointer.mode === 'open';
      const angle = exploratory ? direction + (Math.random() - .5) * .7 : direction;
      const depth = pointer.mode === 'action' ? 0 : pointer.mode === 'code' ? 1 : 2;
      const length = pointer.mode === 'action' ? 72 : pointer.mode === 'code' ? 92 : 96 + Math.random() * 68;
      grow(pointer.x, pointer.y, angle, depth, length, Math.random());
    }
    lastSpawn = performance.now();
    lastPathOrigin = { ...pointer };
    shouldSpawn = false;
  }

  function draw(now) {
    ctx.clearRect(0, 0, innerWidth, pageHeight);
    for (let i = trails.length - 1; i >= 0; i--) {
      const trail = trails[i];
      const age = now - trail.born;
      if (age > trail.duration) { trails.splice(i, 1); continue; }
      const reveal = Math.min(1, age / 480);
      const fade = 1 - Math.pow(age / trail.duration, 1.7);
      const visible = Math.max(2, Math.floor(trail.points.length * reveal));
      ctx.beginPath();
      for (let p = 0; p < visible; p++) {
        const point = trail.points[p];
        if (p === 0) ctx.moveTo(point.x, point.y); else ctx.lineTo(point.x, point.y);
      }
      const end = trail.points[visible - 1];
      const distance = Math.hypot(end.x - trail.source.x, end.y - trail.source.y);
      const alpha = Math.max(0, fade * (.34 - distance / 1250));
      const darkMode = document.documentElement.dataset.theme === 'dark';
      const traceAlpha = darkMode ? Math.min(1, alpha * 2.7) : alpha;
      ctx.strokeStyle = darkMode ? `rgba(240, 236, 226, ${traceAlpha})` : `rgba(28, 27, 24, ${traceAlpha})`;
      ctx.lineWidth = Math.max(.55, 1.22 - trail.depth * .16);
      ctx.stroke();
      ctx.strokeStyle = darkMode ? `rgba(192, 154, 104, ${Math.min(1, traceAlpha * 1.3)})` : `rgba(154, 116, 73, ${alpha * 1.25})`;
      ctx.lineWidth = .8;
      for (let p = 0; p < visible; p += 2) {
        const point = trail.points[p];
        const size = p === 0 || p === visible - 1 ? 3.6 : 2.2;
        ctx.strokeRect(point.x - size / 2, point.y - size / 2, size, size);
      }
    }
    if (pointer && shouldSpawn && now - lastSpawn > spawnEvery) spawn();
    frame = requestAnimationFrame(draw);
  }

  addEventListener('pointermove', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const mode = target?.closest('a, button, input') ? 'action' : target?.closest('pre, code') ? 'code' : 'open';
    pointer = { x: event.clientX, y: event.clientY + scrollY, mode };
    if (!lastPathOrigin || Math.hypot(pointer.x - lastPathOrigin.x, pointer.y - lastPathOrigin.y) > 1) shouldSpawn = true;
  }, { passive: true });
  addEventListener('resize', resize, { passive: true });
  addEventListener('visibilitychange', () => { if (document.hidden) cancelAnimationFrame(frame); else frame = requestAnimationFrame(draw); });
  resize();
  frame = requestAnimationFrame(draw);
})();
