export const mountMemoryControls = (stage, onChoose) => {
  const controls = document.createElement("div");
  controls.className = "memory-controls";
  controls.hidden = true;
  const status = document.createElement("output");
  status.className = "gr-visually-hidden";
  status.setAttribute("aria-live", "polite");
  controls.appendChild(status);
  const panels = new Map();
  for (const [scene, rows] of [
    ["memory-two", 2],
    ["memory-array", 4],
  ]) {
    const panel = document.createElement("div");
    panel.setAttribute("role", "group");
    panel.setAttribute("aria-label", `${rows} location memory controls`);
    panel.dataset.memoryControls = scene;
    panel.hidden = true;
    for (const action of ["Read", "Write"]) {
      const row = document.createElement("div");
      row.className = "memory-control-row";
      for (let address = 0; address < rows; address++) {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.action = action;
        button.dataset.address = String(address);
        button.textContent = `${action} ${address.toString(2).padStart(rows === 2 ? 1 : 2, "0")}`;
        button.setAttribute("aria-pressed", "false");
        row.appendChild(button);
      }
      panel.appendChild(row);
    }
    panels.set(scene, panel);
    controls.appendChild(panel);
  }
  const click = (event) => {
    const button = event.target.closest("button");
    if (!button || !controls.contains(button) || button.disabled) return;

    onChoose(
      button.closest("[data-memory-controls]").dataset.memoryControls,
      button.dataset.action,
      Number(button.dataset.address),
    );
  };
  controls.addEventListener("click", click);
  stage.appendChild(controls);
  const size = new ResizeObserver(([entry]) => {
    stage.style.setProperty(
      "--memory-art-half",
      `${entry.contentRect.height / 2}px`,
    );
  });
  size.observe(stage.querySelector("svg"));

  const update = (scene, state, opacity) => {
    const visible = panels.has(scene);
    controls.hidden = !visible;
    controls.style.opacity = opacity;
    controls.inert = opacity < 0.99;
    stage.style.setProperty("--memory-art-shift", `${opacity * 53}px`);
    stage.style.setProperty("--memory-extra-height", `${opacity * 12}vh`);
    if (visible && !state.busy) {
      const message = `${state.action} ADDR ${state.address.toString(2).padStart(scene === "memory-two" ? 1 : 2, "0")}. Output ${state.output.toString(2).padStart(4, "0")}.`;
      if (status.textContent !== message) status.textContent = message;
    }
    for (const [name, panel] of panels) {
      panel.hidden = name !== scene;
      if (name !== scene) continue;

      for (const button of panel.querySelectorAll("button")) {
        button.setAttribute(
          "aria-pressed",
          String(
            button.dataset.action === state.action &&
              Number(button.dataset.address) === state.address,
          ),
        );
        button.disabled = state.busy;
      }
    }
  };
  const dispose = () => {
    controls.removeEventListener("click", click);
    controls.remove();
    size.disconnect();
    for (const property of [
      "--memory-art-half",
      "--memory-art-shift",
      "--memory-extra-height",
    ])
      stage.style.removeProperty(property);
  };
  return { update, dispose };
};
