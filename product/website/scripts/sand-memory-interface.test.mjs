import assert from "node:assert/strict";
import test from "node:test";
import { MEMORY_INTERFACE_SCENES } from "../src/components/articles/sand/runtime/memory-interface-scenes.js";
import { MEMORY_ACCESS_DURATION } from "../src/components/articles/sand/runtime/memory-access-model.js";

const mountScene = () => {
  const nodes = [];
  const mk = (tag, attributes = {}) => {
    const node = {
      tag,
      attributes: { ...attributes },
      style: {},
      textContent: "",
      opacity: 1,
      x: 0,
      y: 0,
      scale: 1,
      setAttribute(name, value) {
        this.attributes[name] = String(value);
      },
      getAttribute(name) {
        return this.attributes[name];
      },
      querySelectorAll: () => [],
      append() {},
    };
    nodes.push(node);
    return node;
  };
  const scenes = [
    "memory-width",
    "memory-interface",
    "memory-word",
    "memory-address-space",
    "memory-access",
    "memory-block",
    "working-registers",
    "instruction",
    "addressed-memory",
    "instruction-control",
    "program",
  ];
  let position = scenes.indexOf("memory-access");
  let choose;
  const afterRender = [];
  const { demos } = MEMORY_INTERFACE_SCENES.build({
    root: mk("g"),
    tl: { time: () => position },
    hold: 0.18,
    at: () => 0,
    index: (scene) => scenes.indexOf(scene),
    mk,
    group: (attributes) => mk("g", attributes),
    path: (d, attributes) => mk("path", { d, ...attributes }),
    text: (x, y, content, attributes) =>
      Object.assign(mk("text", { x, y, ...attributes }), {
        textContent: String(content),
      }),
    key() {},
    show() {},
    draw() {},
    afterRender,
    controls: {
      register: (_scene, _config, handler) => {
        choose = handler;
      },
      update() {},
    },
  });
  return {
    demos,
    choose: (action) => choose("memory-access", action),
    render: () => afterRender.forEach((callback) => callback()),
    enter: (scene) => {
      position = scenes.indexOf(scene);
    },
    diagram: nodes.find(
      (node) => node.attributes["data-diagram"] === "memory-interface",
    ),
    dispose: () => demos.forEach((animation) => animation.kill()),
  };
};

for (const action of ["Read", "Write"]) {
  test(`${action} resumes after a visibility pause without restarting the transfer`, (t) => {
    const scene = mountScene();
    t.after(scene.dispose);
    scene.render();
    scene.choose(action);
    const animation = scene.demos[1];
    animation.time(1.8);
    scene.render();
    assert.equal(scene.diagram.getAttribute("data-busy"), "true");

    scene.demos.forEach((demo) => demo.pause());
    scene.render();
    assert.equal(animation.paused(), false);
    assert.equal(animation.time(), 1.8);

    animation.time(MEMORY_ACCESS_DURATION);
    scene.render();
    assert.equal(scene.diagram.getAttribute("data-busy"), "false");
    assert.equal(
      scene.diagram.getAttribute("data-mdr"),
      action === "Read" ? "6" : "9",
    );
  });
}

test("memory widening resumes after a visibility pause without replaying", (t) => {
  const scene = mountScene();
  t.after(scene.dispose);
  scene.enter("memory-width");
  scene.render();
  const animation = scene.demos[0];
  animation.time(1.5);
  scene.demos.forEach((demo) => demo.pause());
  scene.render();
  assert.equal(animation.paused(), false);
  assert.equal(animation.time(), 1.5);
  animation.progress(1);
  scene.render();
  assert.equal(animation.progress(), 1);
});
