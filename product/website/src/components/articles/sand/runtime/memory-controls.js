export const mountMemoryControls = (stage, onChoose) => {
  const controls = document.createElement("div");
  controls.className = "memory-controls";
  controls.hidden = true;
  const status = document.createElement("output");
  status.className = "gr-visually-hidden";
  status.setAttribute("aria-live", "polite");
  controls.appendChild(status);
  const panels = new Map();
  const handlers = new Map();
  const configurations = new Map();
  const register = (scene, config, handler = onChoose) => {
    const { rows, addressWidth = rows === 2 ? 1 : 2, compact = false } = config;
    configurations.set(scene, { addressWidth, dataWidth: 4, ...config });
    handlers.set(scene, handler);
    const panel = document.createElement("div");
    panel.setAttribute("role", "group");
    panel.setAttribute("aria-label", `${rows} location memory controls`);
    panel.dataset.memoryControls = scene;
    panel.hidden = true;
    const actions = compact ? [["Read", "Write"]] : [["Read"], ["Write"]];
    for (const group of actions) {
      const row = document.createElement("div");
      row.className = "memory-control-row";
      for (const action of group) {
        for (const address of config.addresses ??
          Array.from({ length: rows }, (_, i) => i)) {
          const button = document.createElement("button");
          button.type = "button";
          button.dataset.action = action;
          button.dataset.address = String(address);
          button.textContent = compact
            ? action
            : `${action} ${address.toString(2).padStart(addressWidth, "0")}`;
          button.setAttribute("aria-pressed", "false");
          row.appendChild(button);
        }
      }
      panel.appendChild(row);
    }
    if (config.prompt) {
      const prompt = document.createElement("p");
      prompt.className = "memory-control-prompt";
      prompt.textContent = config.prompt;
      panel.appendChild(prompt);
    }
    panels.set(scene, panel);
    controls.appendChild(panel);
  };
  register("memory-two", { rows: 2 });
  register("memory-array", { rows: 4 });
  const click = (event) => {
    const button = event.target.closest("button");
    if (!button || !controls.contains(button) || button.disabled) return;

    const scene = button.closest("[data-memory-controls]").dataset
      .memoryControls;
    handlers.get(scene)(
      scene,
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
      const config = configurations.get(scene);
      const message = `${state.action} ADDR ${state.address.toString(2).padStart(config.addressWidth, "0")}. Output ${state.output.toString(2).padStart(config.dataWidth, "0")}.`;
      if (status.textContent !== message) status.textContent = message;
    }
    for (const [name, panel] of panels) {
      panel.hidden = name !== scene;
      if (name !== scene) continue;

      const prompt = panel.querySelector(".memory-control-prompt");
      if (
        prompt &&
        state.prompt !== undefined &&
        prompt.textContent !== state.prompt
      )
        prompt.textContent = state.prompt;

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
  return { register, update, dispose };
};
