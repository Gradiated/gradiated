import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

import type { DeckLayout, PlateLayout } from "./layout";
import type { ExplorerModel, ModuleView } from "./model";

// Shaders read per-plate state from one float texture: r = base x,
// g = accordion offset, b = glow, a = reveal threshold.

export type Pick =
  | { kind: "module"; plate: number; module: ModuleView }
  | { kind: "expert"; plate: number; expert: number }
  | { kind: "plate"; plate: number };

export type SceneCallbacks = {
  hover: (pick: Pick | null) => void;
  select: (pick: Pick | null) => void;
  tour: (running: boolean) => void;
  interact: () => void;
};

const SHARED = /* glsl */ `
  uniform sampler2D uPlates;
  uniform float uReveal;
  uniform float uFocus;
  uniform float uFocusMix;
  vec4 plateInfo(float plate) {
    return texelFetch(uPlates, ivec2(int(plate + 0.5), 0), 0);
  }
  float revealOf(float threshold) {
    return smoothstep(threshold, threshold + 0.14, uReveal);
  }
  // Plates the adapter leaves unchanged recede so the changed ones stand out.
  float dimOf(float plate) {
    if (abs(plate - uFocus) < 0.5) return 1.0;
    float quiet = plateInfo(plate).b > 0.001 ? 1.0 : 0.22;
    return quiet * mix(1.0, 0.1, uFocusMix);
  }
  // Plates between the camera and the focused plate shrink away.
  float hiddenOf(float plate) {
    return uFocus >= 0.0 && plate < uFocus - 0.5 ? uFocusMix : 0.0;
  }
  vec4 placed(vec4 world, float plate, float offset) {
    float hide = hiddenOf(plate);
    world.x += offset;
    world.yz *= 1.0 - hide;
    return world;
  }
  vec3 heatRamp(float t) {
    t = clamp(t, 0.0, 1.0);
    vec3 c0 = vec3(0.015, 0.06, 0.07);
    vec3 c1 = vec3(0.0, 0.36, 0.34);
    vec3 c2 = vec3(0.34, 0.86, 0.16);
    vec3 c3 = vec3(1.0, 0.78, 0.22);
    vec3 c4 = vec3(1.0, 0.97, 0.88);
    if (t < 0.25) return mix(c0, c1, t / 0.25);
    if (t < 0.5) return mix(c1, c2, (t - 0.25) / 0.25);
    if (t < 0.75) return mix(c2, c3, (t - 0.5) / 0.25);
    return mix(c3, c4, (t - 0.75) / 0.25);
  }
`;

const PANEL_VERTEX = /* glsl */ `
  ${SHARED}
  attribute float aPlate;
  attribute vec4 aAtlas;
  attribute vec4 aInfo;
  attribute vec2 aCells;
  attribute float aState;
  varying vec2 vUv;
  varying vec4 vAtlas;
  varying vec4 vInfo;
  varying vec2 vCells;
  varying float vState;
  varying float vFade;
  void main() {
    vUv = uv;
    vAtlas = aAtlas;
    vInfo = aInfo;
    vCells = aCells;
    vState = aState;
    vec4 plate = plateInfo(aPlate);
    vFade = revealOf(plate.a) * dimOf(aPlate) * (1.0 - hiddenOf(aPlate));
    vec4 world = placed(modelMatrix * instanceMatrix * vec4(position, 1.0), aPlate, plate.g);
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

const PANEL_FRAGMENT = /* glsl */ `
  ${SHARED}
  uniform sampler2D uAtlas;
  uniform float uTime;
  varying vec2 vUv;
  varying vec4 vAtlas;
  varying vec4 vInfo;
  varying vec2 vCells;
  varying float vState;
  varying float vFade;
  void main() {
    float intensity = vInfo.x;
    float adapted = vInfo.y;
    vec2 size = vInfo.zw;
    // Near edge-on, interpolation can stray outside the quad.
    vec2 uv = clamp(vUv, 0.0, 1.0);
    vec2 cell = vec2(uv.x, 1.0 - uv.y);
    float heat = texture2D(uAtlas, vAtlas.xy + clamp(cell, 0.0005, 0.9995) * vAtlas.zw).r;

    vec2 grid = cell * vCells;
    vec2 width = max(fwidth(grid), vec2(1e-4));
    vec2 distance = min(fract(grid), 1.0 - fract(grid)) / width;
    float line = (1.0 - clamp(min(distance.x, distance.y) - 0.5, 0.0, 1.0))
      * (1.0 - smoothstep(0.1, 0.3, max(width.x, width.y)));

    float hover = step(0.5, vState) * (1.0 - step(1.5, vState));
    float selected = step(1.5, vState);
    vec2 edge = min(uv, 1.0 - uv) * size;
    float border = 1.0 - smoothstep(0.0, 0.012 + selected * 0.012, min(edge.x, edge.y));

    float value = intensity * (0.14 + 0.86 * heat);
    vec3 hot = heatRamp(value) * (0.22 + 1.5 * value * value);
    vec3 frozen = vec3(0.03, 0.045, 0.065) + vec3(0.02, 0.03, 0.045) * (1.0 - line);
    vec3 color = mix(frozen, hot * (1.0 - line * 0.4), adapted);
    vec3 rim = mix(vec3(0.13, 0.19, 0.27), heatRamp(0.4 + 0.6 * intensity) * 1.2, adapted);
    rim = mix(rim, vec3(2.2), max(hover * 0.55, selected * (0.7 + 0.3 * sin(uTime * 4.0))));
    color = mix(color, rim, border) + hover * 0.06;
    gl_FragColor = vec4(color * vFade, 1.0);
  }
`;

const PLATE_VERTEX = /* glsl */ `
  ${SHARED}
  attribute float aPlate;
  attribute vec2 aSize;
  varying vec2 vUv;
  varying vec2 vSize;
  varying float vGlow;
  varying float vFade;
  varying float vFocused;
  varying float vDepth;
  void main() {
    vUv = uv;
    vSize = aSize;
    vec4 plate = plateInfo(aPlate);
    vGlow = plate.b;
    vFade = revealOf(plate.a) * dimOf(aPlate) * (1.0 - hiddenOf(aPlate));
    vFocused = abs(aPlate - uFocus) < 0.5 ? uFocusMix : 0.0;
    vec4 world = placed(modelMatrix * instanceMatrix * vec4(position, 1.0), aPlate, plate.g);
    vec4 view = viewMatrix * world;
    vDepth = -view.z;
    gl_Position = projectionMatrix * view;
  }
`;

const PLATE_FRAGMENT = /* glsl */ `
  ${SHARED}
  varying vec2 vUv;
  varying vec2 vSize;
  varying float vGlow;
  varying float vFade;
  varying float vFocused;
  varying float vDepth;
  void main() {
    // Near edge-on, interpolation can stray outside the quad; unclamped, the
    // halo below overflows to infinity and bloom smears it over the frame.
    vec2 uv = clamp(vUv, 0.0, 1.0);
    vec2 edge = min(uv, 1.0 - uv) * vSize;
    float d = max(min(edge.x, edge.y), 0.0);
    float rim = 1.0 - smoothstep(0.0, 0.02, d);
    float halo = exp(-d * 9.0);
    vec3 tint = mix(vec3(0.3, 0.45, 0.62), heatRamp(0.45 + 0.55 * vGlow), step(0.001, vGlow));
    float strength = 0.012 + rim * 0.3 * (1.0 + vFocused * 0.5) + halo * (0.03 + vGlow * 0.1);
    // Glass right in front of the camera would wash out the frame.
    gl_FragColor = vec4(tint * strength * vFade * smoothstep(0.6, 4.5, vDepth), 1.0);
  }
`;

const EXPERT_VERTEX = /* glsl */ `
  ${SHARED}
  uniform float uHover;
  attribute float aPlate;
  attribute float aGlow;
  varying float vShade;
  varying float vGlow;
  varying float vFade;
  varying float vHover;
  void main() {
    vec4 plate = plateInfo(aPlate);
    vFade = revealOf(plate.a) * dimOf(aPlate) * (1.0 - hiddenOf(aPlate));
    vGlow = aGlow;
    vHover = abs(float(gl_InstanceID) - uHover) < 0.5 ? 1.0 : 0.0;
    vec3 n = normalize(mat3(instanceMatrix) * normal);
    vShade = 0.45 + 0.55 * max(dot(n, normalize(vec3(-0.7, 0.75, 0.35))), 0.0);
    vec4 world = placed(modelMatrix * instanceMatrix * vec4(position, 1.0), aPlate, plate.g);
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

const EXPERT_FRAGMENT = /* glsl */ `
  ${SHARED}
  varying float vShade;
  varying float vGlow;
  varying float vFade;
  varying float vHover;
  void main() {
    vec3 frozen = vec3(0.085, 0.13, 0.2) * vShade;
    vec3 hot = heatRamp(0.3 + 0.7 * vGlow) * (0.4 + 1.6 * vGlow) * vShade;
    vec3 color = mix(frozen, hot, step(0.001, vGlow)) + vHover * vec3(0.9, 1.0, 1.1);
    gl_FragColor = vec4(color * vFade, 1.0);
  }
`;

const TERRAIN_VERTEX = /* glsl */ `
  ${SHARED}
  uniform float uGrow;
  attribute float aHeight;
  attribute float aValue;
  varying float vValue;
  varying float vShade;
  void main() {
    vValue = aValue;
    vec3 p = position;
    p.x *= aHeight * uGrow;
    vec3 n = normalize(mat3(instanceMatrix) * normal);
    vShade = 0.55 + 0.45 * max(dot(n, normalize(vec3(-0.8, 0.6, 0.3))), 0.0);
    gl_Position = projectionMatrix * viewMatrix * modelMatrix * instanceMatrix * vec4(p, 1.0);
  }
`;

const TERRAIN_FRAGMENT = /* glsl */ `
  ${SHARED}
  varying float vValue;
  varying float vShade;
  void main() {
    vec3 color = heatRamp(vValue) * (0.25 + 1.3 * vValue * vValue) * vShade;
    gl_FragColor = vec4(color, 1.0);
  }
`;

const GROUND_FRAGMENT = /* glsl */ `
  uniform vec2 uCenter;
  uniform float uRadius;
  varying vec3 vWorld;
  void main() {
    vec2 p = vWorld.xz;
    vec2 g = abs(fract(p) - 0.5) / max(fwidth(p), vec2(1e-4));
    float line = 1.0 - clamp(min(g.x, g.y), 0.0, 1.0);
    float fade = 1.0 - smoothstep(0.2, 1.0, length((p - uCenter) / uRadius));
    gl_FragColor = vec4(vec3(0.12, 0.2, 0.3) * line * fade * fade * 0.28, 1.0);
  }
`;

const easeInOut = (t: number) =>
  t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

type Flight = {
  fromPosition: THREE.Vector3;
  toPosition: THREE.Vector3;
  fromTarget: THREE.Vector3;
  toTarget: THREE.Vector3;
  start: number;
  duration: number;
};

type Label = {
  element: HTMLDivElement;
  plate: number;
  position: THREE.Vector3;
  /** Right edge of the panel; the label is clipped to the panel's width. */
  end?: THREE.Vector3;
};

export const webglAvailable = () => {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2"));
  } catch {
    return false;
  }
};

export class ExplorerScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly composer: EffectComposer;
  private readonly bloom: UnrealBloomPass;
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.PerspectiveCamera;
  private readonly controls: OrbitControls;
  private last = 0;
  private readonly plateData: Float32Array;
  private readonly plateTexture: THREE.DataTexture;
  private readonly atlasSlots = new Map<
    number,
    [number, number, number, number]
  >();
  private readonly atlas: THREE.DataTexture;
  private readonly shared: Record<string, THREE.IUniform>;
  private readonly panelState: THREE.InstancedBufferAttribute;
  private readonly expertOwners: { plate: number; first: number }[] = [];
  private readonly expertMaterial?: THREE.ShaderMaterial;
  private terrain: THREE.InstancedMesh | undefined;
  private readonly terrainUniforms = { uGrow: { value: 0 } };
  private readonly offsets: number[];
  private readonly targetOffsets: number[];
  private focusTarget = 0;
  private focused: number | null = null;
  private hovered: Pick | null = null;
  private selected: number | null = null;
  private flight: Flight | undefined;
  private touring: { s: number } | undefined;
  private revealStart = 0;
  private time = 0;
  private frame = 0;
  private readonly observer: ResizeObserver;
  private readonly labelLayer: HTMLDivElement;
  private labels: Label[] = [];
  private readonly raycaster = new THREE.Raycaster();
  private pointerDown: { x: number; y: number } | undefined;
  private readonly cleanups: (() => void)[] = [];
  private inset = 0;

  constructor(
    private readonly container: HTMLElement,
    private readonly model: ExplorerModel,
    private readonly layout: DeckLayout,
    private readonly callbacks: SceneCallbacks,
    private readonly reducedMotion: boolean,
    inset = 0,
  ) {
    this.inset = inset;
    const width = Math.max(container.clientWidth, 1);
    const height = Math.max(container.clientHeight, 1);
    this.renderer = new THREE.WebGLRenderer({
      antialias: false,
      powerPreference: "high-performance",
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(width, height);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.domElement.style.display = "block";
    this.renderer.domElement.style.touchAction = "none";
    container.append(this.renderer.domElement);

    this.labelLayer = document.createElement("div");
    this.labelLayer.className =
      "pointer-events-none absolute inset-0 overflow-hidden";
    container.append(this.labelLayer);

    this.scene.background = new THREE.Color(0x030508);
    this.scene.fog = new THREE.FogExp2(
      0x030508,
      0.9 / Math.max(layout.end - layout.start, 12),
    );
    this.camera = new THREE.PerspectiveCamera(
      42,
      width / height,
      0.05,
      (layout.end - layout.start) * 8 + 200,
    );

    const plates = layout.plates;
    this.offsets = plates.map(() => 0);
    this.targetOffsets = plates.map(() => 0);
    this.plateData = new Float32Array(plates.length * 4);
    plates.forEach((plate, index) => {
      this.plateData[index * 4] = plate.x;
      this.plateData[index * 4 + 2] = plate.intensity;
      this.plateData[index * 4 + 3] = reducedMotion
        ? -1
        : (index / Math.max(plates.length - 1, 1)) * 0.86;
    });
    this.plateTexture = new THREE.DataTexture(
      this.plateData,
      plates.length,
      1,
      THREE.RGBAFormat,
      THREE.FloatType,
    );
    this.plateTexture.needsUpdate = true;
    this.shared = {
      uPlates: { value: this.plateTexture },
      uReveal: { value: reducedMotion ? 2 : 0 },
      uFocus: { value: -1 },
      uFocusMix: { value: 0 },
      uTime: { value: 0 },
    };

    this.atlas = this.buildAtlas();
    const panels = this.buildPanels();
    this.panelState = panels.state;
    this.scene.add(panels.mesh);
    this.scene.add(this.buildPlates());
    const experts = this.buildExperts();
    if (experts) {
      this.expertMaterial = experts.material;
      this.scene.add(experts.mesh);
    }
    this.scene.add(this.buildGround());

    const target = new THREE.WebGLRenderTarget(width, height, {
      type: THREE.HalfFloatType,
      samples: 4,
    });
    this.composer = new EffectComposer(this.renderer, target);
    this.composer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.composer.setSize(width, height);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(
      new THREE.Vector2(width, height),
      0.3,
      0.4,
      0.6,
    );
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.rotateSpeed = 0.55;
    this.controls.zoomSpeed = 0.9;
    this.controls.zoomToCursor = true;
    this.controls.minDistance = 0.4;
    this.controls.maxDistance = (layout.end - layout.start) * 3 + 30;
    this.controls.addEventListener("start", () => {
      this.flight = undefined;
      this.stopTour();
      this.callbacks.interact();
    });

    const overview = this.overviewPose();
    if (reducedMotion) {
      this.camera.position.copy(overview.position);
      this.controls.target.copy(overview.target);
    } else {
      const first = plates[0]!;
      this.camera.position.set(
        first.x - 2.5,
        layout.height * 0.18,
        layout.width * 0.55,
      );
      this.controls.target.set(first.x + 6, 0, 0);
      this.flyTo(overview.position, overview.target, 3200, 250);
    }
    this.resize();
    this.controls.update();
    this.setOverviewLabels();

    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(container);
    this.bindPointer();
    this.revealStart = performance.now();
    this.frame = requestAnimationFrame(this.loop);
  }

  private buildAtlas() {
    const adapted = this.layout.panels.filter((panel) => panel.module.heatmap);
    const cell = Math.max(
      1,
      ...adapted.map(({ module }) =>
        Math.max(module.heatmap!.rows, module.heatmap!.columns),
      ),
    );
    const perRow = Math.max(1, Math.floor(2048 / cell));
    const width = Math.max(1, Math.min(adapted.length, perRow) * cell);
    const height = Math.max(1, Math.ceil(adapted.length / perRow) * cell);
    const data = new Uint8Array(width * height);
    adapted.forEach(({ module }, slot) => {
      const heatmap = module.heatmap!;
      const x = (slot % perRow) * cell;
      const y = Math.floor(slot / perRow) * cell;
      for (let row = 0; row < heatmap.rows; row++)
        for (let column = 0; column < heatmap.columns; column++)
          data[(y + row) * width + x + column] =
            heatmap.values[row * heatmap.columns + column] ?? 0;
      this.atlasSlots.set(module.index, [
        x / width,
        y / height,
        heatmap.columns / width,
        heatmap.rows / height,
      ]);
    });
    const texture = new THREE.DataTexture(
      data,
      width,
      height,
      THREE.RedFormat,
      THREE.UnsignedByteType,
    );
    texture.unpackAlignment = 1;
    texture.magFilter = THREE.NearestFilter;
    texture.minFilter = THREE.NearestFilter;
    texture.needsUpdate = true;
    return texture;
  }

  private buildPanels() {
    const panels = this.layout.panels;
    const geometry = new THREE.PlaneGeometry(1, 1);
    geometry.rotateY(-Math.PI / 2);
    const count = Math.max(panels.length, 1);
    const plate = new Float32Array(count);
    const atlas = new Float32Array(count * 4);
    const info = new Float32Array(count * 4);
    const cells = new Float32Array(count * 2);
    const state = new THREE.InstancedBufferAttribute(
      new Float32Array(count),
      1,
    );
    state.setUsage(THREE.DynamicDrawUsage);
    const material = new THREE.ShaderMaterial({
      vertexShader: PANEL_VERTEX,
      fragmentShader: PANEL_FRAGMENT,
      uniforms: { ...this.shared, uAtlas: { value: this.atlas } },
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.InstancedMesh(geometry, material, count);
    const matrix = new THREE.Matrix4();
    panels.forEach((panel, index) => {
      const x = this.layout.plates[panel.plate]!.x - 0.012;
      matrix.compose(
        new THREE.Vector3(x, panel.v, panel.u),
        new THREE.Quaternion(),
        new THREE.Vector3(1, panel.height, panel.width),
      );
      mesh.setMatrixAt(index, matrix);
      plate[index] = panel.plate;
      atlas.set(
        this.atlasSlots.get(panel.module.index) ?? [0, 0, 0, 0],
        index * 4,
      );
      info.set(
        [
          panel.module.intensity,
          panel.module.adapted ? 1 : 0,
          panel.width,
          panel.height,
        ],
        index * 4,
      );
      cells.set(
        panel.module.heatmap
          ? [panel.module.heatmap.columns, panel.module.heatmap.rows]
          : [
              Math.min(16, Math.max(2, Math.round(panel.width * 24))),
              Math.min(16, Math.max(2, Math.round(panel.height * 24))),
            ],
        index * 2,
      );
    });
    if (!panels.length) mesh.count = 0;
    geometry.setAttribute(
      "aPlate",
      new THREE.InstancedBufferAttribute(plate, 1),
    );
    geometry.setAttribute(
      "aAtlas",
      new THREE.InstancedBufferAttribute(atlas, 4),
    );
    geometry.setAttribute("aInfo", new THREE.InstancedBufferAttribute(info, 4));
    geometry.setAttribute(
      "aCells",
      new THREE.InstancedBufferAttribute(cells, 2),
    );
    geometry.setAttribute("aState", state);
    mesh.frustumCulled = false;
    return { mesh, state };
  }

  private buildPlates() {
    const plates = this.layout.plates;
    const geometry = new THREE.PlaneGeometry(1, 1);
    geometry.rotateY(-Math.PI / 2);
    const plate = new Float32Array(plates.length);
    const size = new Float32Array(plates.length * 2);
    const material = new THREE.ShaderMaterial({
      vertexShader: PLATE_VERTEX,
      fragmentShader: PLATE_FRAGMENT,
      uniforms: this.shared,
      side: THREE.DoubleSide,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const mesh = new THREE.InstancedMesh(geometry, material, plates.length);
    const matrix = new THREE.Matrix4();
    plates.forEach((entry, index) => {
      matrix.compose(
        new THREE.Vector3(entry.x, 0, 0),
        new THREE.Quaternion(),
        new THREE.Vector3(1, entry.height, entry.width),
      );
      mesh.setMatrixAt(index, matrix);
      plate[index] = index;
      size.set([entry.width, entry.height], index * 2);
    });
    geometry.setAttribute(
      "aPlate",
      new THREE.InstancedBufferAttribute(plate, 1),
    );
    geometry.setAttribute("aSize", new THREE.InstancedBufferAttribute(size, 2));
    mesh.frustumCulled = false;
    mesh.renderOrder = 2;
    return mesh;
  }

  private buildExperts() {
    const layers = this.layout.plates.filter((plate) => plate.experts);
    if (!layers.length) return undefined;

    const total = layers.reduce((sum, plate) => sum + plate.experts!.count, 0);
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    const plateIndex = new Float32Array(total);
    const glow = new Float32Array(total);
    const material = new THREE.ShaderMaterial({
      vertexShader: EXPERT_VERTEX,
      fragmentShader: EXPERT_FRAGMENT,
      uniforms: { ...this.shared, uHover: { value: -1 } },
    });
    const mesh = new THREE.InstancedMesh(geometry, material, total);
    const matrix = new THREE.Matrix4();
    const position = new THREE.Vector3();
    const scale = new THREE.Vector3();
    const rotation = new THREE.Quaternion();
    let instance = 0;
    for (const plate of layers) {
      const grid = plate.experts!;
      const pitch = grid.size + grid.gap;
      const left = -(grid.columns * pitch - grid.gap) / 2;
      const top = grid.v + (grid.rows * pitch - grid.gap) / 2;
      const intensity = Math.max(
        0,
        ...this.model.modules
          .filter(
            (module) =>
              module.layer === plate.layer && module.group === "experts",
          )
          .map((module) => module.intensity),
      );
      this.expertOwners.push({ plate: plate.index, first: instance });
      for (let expert = 0; expert < grid.count; expert++) {
        const column = expert % grid.columns;
        const row = Math.floor(expert / grid.columns);
        position.set(
          plate.x,
          top - row * pitch - grid.size / 2,
          left + column * pitch + grid.size / 2,
        );
        scale.set(grid.size * 0.6, grid.size, grid.size);
        matrix.compose(position, rotation, scale);
        mesh.setMatrixAt(instance, matrix);
        plateIndex[instance] = plate.index;
        glow[instance] = intensity;
        instance++;
      }
    }
    geometry.setAttribute(
      "aPlate",
      new THREE.InstancedBufferAttribute(plateIndex, 1),
    );
    geometry.setAttribute("aGlow", new THREE.InstancedBufferAttribute(glow, 1));
    mesh.frustumCulled = false;
    return { mesh, material };
  }

  private buildGround() {
    const length = this.layout.end - this.layout.start;
    const radius = Math.max(length, 20);
    const geometry = new THREE.PlaneGeometry(radius * 3, radius * 3);
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.ShaderMaterial({
      vertexShader: /* glsl */ `
        varying vec3 vWorld;
        void main() {
          vec4 world = modelMatrix * vec4(position, 1.0);
          vWorld = world.xyz;
          gl_Position = projectionMatrix * viewMatrix * world;
        }
      `,
      fragmentShader: GROUND_FRAGMENT,
      uniforms: {
        uCenter: {
          value: new THREE.Vector2(
            (this.layout.start + this.layout.end) / 2,
            0,
          ),
        },
        uRadius: { value: radius * 0.85 },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(
      (this.layout.start + this.layout.end) / 2,
      -this.layout.height / 2 - 0.9,
      0,
    );
    return mesh;
  }

  private overviewPose() {
    const center = new THREE.Vector3(
      (this.layout.start + this.layout.end) / 2,
      0,
      0,
    );
    const length = this.layout.end - this.layout.start;
    const radius = Math.hypot(
      length / 2,
      this.layout.height / 2,
      this.layout.width / 2,
    );
    const fov = THREE.MathUtils.degToRad(this.camera.fov);
    const fit = Math.max(
      radius / Math.sin(fov / 2),
      radius / Math.sin(Math.atan(Math.tan(fov / 2) * this.visibleAspect())),
    );
    const direction = new THREE.Vector3(-0.3, 0.3, 0.9).normalize();
    return {
      target: center,
      position: center.clone().addScaledVector(direction, fit * 0.64),
    };
  }

  private headerInset(height: number) {
    return height > 520 ? 120 : 0;
  }

  private visibleAspect() {
    const width = Math.max(this.container.clientWidth, 1);
    const height = Math.max(this.container.clientHeight, 1);
    return (
      Math.max(width - Math.min(this.inset, width * 0.5), 1) /
      Math.max(height - this.headerInset(height), 1)
    );
  }

  private platePose(index: number) {
    const plate = this.layout.plates[index]!;
    const x = plate.x + (this.targetOffsets[index] ?? 0);
    const fov = THREE.MathUtils.degToRad(this.camera.fov);
    const distance =
      (Math.max(plate.height, plate.width / this.visibleAspect()) /
        (2 * Math.tan(fov / 2))) *
      1.5;
    return {
      target: new THREE.Vector3(x, 0, 0),
      position: new THREE.Vector3(
        x - distance * 0.96,
        plate.height * 0.08,
        distance * 0.26,
      ),
    };
  }

  private flyTo(
    position: THREE.Vector3,
    target: THREE.Vector3,
    duration = 1100,
    delay = 0,
  ) {
    if (this.reducedMotion) {
      this.camera.position.copy(position);
      this.controls.target.copy(target);
      this.controls.update();
      return;
    }
    this.flight = {
      fromPosition: this.camera.position.clone(),
      toPosition: position,
      fromTarget: this.controls.target.clone(),
      toTarget: target,
      start: performance.now() + delay,
      duration,
    };
  }

  focus(index: number | null) {
    this.stopTour();
    this.focused = index;
    this.layout.plates.forEach((_, plate) => {
      this.targetOffsets[plate] =
        index === null || plate === index
          ? 0
          : Math.sign(plate - index) * Math.min(2.6, this.layout.width * 0.5);
    });
    this.focusTarget = index === null ? 0 : 1;
    this.shared.uFocus!.value = index ?? -1;
    this.buildTerrain(index);
    if (index === null) {
      const pose = this.overviewPose();
      this.flyTo(pose.position, pose.target, 1300);
      this.setOverviewLabels();
    } else {
      const pose = this.platePose(index);
      this.flyTo(pose.position, pose.target, 1150);
      this.setPlateLabels(index);
    }
  }

  select(moduleIndex: number | null) {
    const panels = this.layout.panels;
    const previous = this.selected;
    this.selected = moduleIndex;
    for (const index of [previous, moduleIndex]) {
      const instance = panels.findIndex(
        (panel) => panel.module.index === index,
      );
      if (instance >= 0)
        this.panelState.setX(
          instance,
          index === moduleIndex && moduleIndex !== null ? 2 : 0,
        );
    }
    this.panelState.needsUpdate = true;
  }

  tour() {
    if (this.reducedMotion) return;

    this.focus(null);
    this.flight = undefined;
    this.touring = { s: -0.6 };
    this.callbacks.tour(true);
  }

  stopTour() {
    if (!this.touring) return;

    this.touring = undefined;
    this.callbacks.tour(false);
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    for (const cleanup of this.cleanups) cleanup();
    this.controls.dispose();
    this.disposeTerrain();
    this.scene.traverse((object) => {
      const mesh = object as THREE.Mesh;
      mesh.geometry?.dispose();
      const material = mesh.material as
        THREE.Material | THREE.Material[] | undefined;
      if (Array.isArray(material)) material.forEach((entry) => entry.dispose());
      else material?.dispose();
    });
    this.atlas.dispose();
    this.plateTexture.dispose();
    this.composer.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.renderer.domElement.remove();
    this.labelLayer.remove();
  }

  private disposeTerrain() {
    if (!this.terrain) return;

    this.scene.remove(this.terrain);
    this.terrain.geometry.dispose();
    (this.terrain.material as THREE.Material).dispose();
    this.terrain = undefined;
  }

  private buildTerrain(index: number | null) {
    this.disposeTerrain();
    if (index === null) return;

    const plate = this.layout.plates[index]!;
    const panels = plate.panels.filter((panel) => panel.module.heatmap);
    const total = panels.reduce(
      (sum, panel) =>
        sum + panel.module.heatmap!.rows * panel.module.heatmap!.columns,
      0,
    );
    if (!total) return;

    const geometry = new THREE.BoxGeometry(1, 1, 1);
    geometry.translate(-0.5, 0, 0);
    const heights = new Float32Array(total);
    const values = new Float32Array(total);
    const material = new THREE.ShaderMaterial({
      vertexShader: TERRAIN_VERTEX,
      fragmentShader: TERRAIN_FRAGMENT,
      uniforms: { ...this.shared, ...this.terrainUniforms },
    });
    const mesh = new THREE.InstancedMesh(geometry, material, total);
    const matrix = new THREE.Matrix4();
    const rotation = new THREE.Quaternion();
    let instance = 0;
    for (const panel of panels) {
      const heatmap = panel.module.heatmap!;
      const cellWidth = panel.width / heatmap.columns;
      const cellHeight = panel.height / heatmap.rows;
      const depth = Math.min(
        1.1,
        0.25 + Math.max(panel.width, panel.height) * 0.5,
      );
      for (let row = 0; row < heatmap.rows; row++)
        for (let column = 0; column < heatmap.columns; column++) {
          const heat =
            (heatmap.values[row * heatmap.columns + column] ?? 0) / 255;
          matrix.compose(
            new THREE.Vector3(
              plate.x - 0.02,
              panel.v + panel.height / 2 - (row + 0.5) * cellHeight,
              panel.u - panel.width / 2 + (column + 0.5) * cellWidth,
            ),
            rotation,
            new THREE.Vector3(1, cellHeight * 0.84, cellWidth * 0.84),
          );
          mesh.setMatrixAt(instance, matrix);
          const value = panel.module.intensity * (0.14 + 0.86 * heat);
          values[instance] = value;
          heights[instance] =
            (0.015 + heat * heat * 0.985) * depth * panel.module.intensity;
          instance++;
        }
    }
    geometry.setAttribute(
      "aHeight",
      new THREE.InstancedBufferAttribute(heights, 1),
    );
    geometry.setAttribute(
      "aValue",
      new THREE.InstancedBufferAttribute(values, 1),
    );
    mesh.frustumCulled = false;
    this.terrainUniforms.uGrow.value = this.reducedMotion ? 1 : 0;
    this.terrain = mesh;
    this.scene.add(mesh);
  }

  private clearLabels() {
    for (const label of this.labels) label.element.remove();
    this.labels = [];
  }

  private addLabel(
    plate: number,
    position: THREE.Vector3,
    title: string,
    detail?: string,
    tone: "plate" | "panel" = "plate",
    end?: THREE.Vector3,
  ) {
    const element = document.createElement("div");
    element.className =
      tone === "plate"
        ? "absolute left-0 top-0 -translate-x-1/2 -translate-y-full whitespace-nowrap pb-1 font-mono text-[10px] uppercase tracking-[0.18em] text-sky-100/70 will-change-transform"
        : "absolute left-0 top-0 -translate-y-full overflow-hidden text-ellipsis whitespace-nowrap pb-0.5 font-mono text-[10px] leading-tight text-white/85 will-change-transform";
    element.textContent = title;
    if (detail) {
      const span = document.createElement("span");
      span.className = "ml-1.5 text-white/45";
      span.textContent = detail;
      element.append(span);
    }
    this.labelLayer.append(element);
    this.labels.push({ element, plate, position, ...(end ? { end } : {}) });
  }

  private plateTitle(plate: PlateLayout) {
    return plate.kind === "embedding"
      ? "Embedding"
      : plate.kind === "head"
        ? "Output head"
        : `Layer ${plate.layer}`;
  }

  private setOverviewLabels() {
    this.clearLabels();
    const plates = this.layout.plates;
    const step = Math.max(1, Math.ceil(this.model.layerCount / 8));
    for (const plate of plates)
      if (
        plate.kind !== "layer" ||
        (plate.layer! % step === 0 &&
          this.model.layerCount - plate.layer! > step / 2)
      )
        this.addLabel(
          plate.index,
          new THREE.Vector3(plate.x, plate.height / 2 + 0.08, 0),
          this.plateTitle(plate),
        );
  }

  private setPlateLabels(index: number) {
    this.clearLabels();
    const plate = this.layout.plates[index]!;
    this.addLabel(
      index,
      new THREE.Vector3(plate.x, plate.height / 2 + 0.08, 0),
      this.plateTitle(plate),
    );
    for (const panel of plate.panels)
      this.addLabel(
        index,
        new THREE.Vector3(
          plate.x - 0.02,
          panel.v + panel.height / 2 + 0.02,
          panel.u - panel.width / 2,
        ),
        panel.module.label,
        panel.module.adapted ? undefined : "frozen",
        "panel",
        new THREE.Vector3(
          plate.x - 0.02,
          panel.v + panel.height / 2 + 0.02,
          panel.u + panel.width / 2,
        ),
      );
    if (plate.experts)
      this.addLabel(
        index,
        new THREE.Vector3(
          plate.x - 0.02,
          plate.experts.v +
            (plate.experts.rows * (plate.experts.size + plate.experts.gap)) /
              2 +
            0.02,
          -(plate.experts.columns * (plate.experts.size + plate.experts.gap)) /
            2,
        ),
        `${plate.experts.count} routed experts`,
        this.model.modules.some(
          (module) =>
            module.layer === plate.layer && module.group === "experts",
        )
          ? undefined
          : "frozen",
        "panel",
      );
  }

  private updateLabels() {
    if (!this.labels.length) return;

    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    const point = new THREE.Vector3();
    for (const label of this.labels) {
      point.copy(label.position);
      point.x += this.offsets[label.plate] ?? 0;
      point.project(this.camera);
      const visible =
        point.z < 1 && Math.abs(point.x) < 1.2 && Math.abs(point.y) < 1.2;
      label.element.style.opacity = visible
        ? String(
            this.revealOf(label.plate) *
              (this.focused === null || this.focused === label.plate
                ? 1
                : 0.25),
          )
        : "0";
      const left = ((point.x + 1) / 2) * width;
      label.element.style.transform = `translate(${left}px, ${((1 - point.y) / 2) * height}px)`;
      if (label.end) {
        point.copy(label.end);
        point.x += this.offsets[label.plate] ?? 0;
        point.project(this.camera);
        const span = ((point.x + 1) / 2) * width - left;
        label.element.style.maxWidth = `${Math.max(span, 0)}px`;
        if (span < 28) label.element.style.opacity = "0";
      }
    }
  }

  private revealOf(plate: number) {
    const threshold = this.plateData[plate * 4 + 3] ?? 0;
    const value = this.shared.uReveal!.value as number;
    return THREE.MathUtils.clamp((value - threshold) / 0.14, 0, 1);
  }

  private pick(clientX: number, clientY: number): Pick | null {
    const bounds = this.renderer.domElement.getBoundingClientRect();
    const pointer = new THREE.Vector2(
      ((clientX - bounds.left) / bounds.width) * 2 - 1,
      -((clientY - bounds.top) / bounds.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(pointer, this.camera);
    const { origin, direction } = this.raycaster.ray;
    if (Math.abs(direction.x) < 1e-6) return null;

    let solid: { pick: Pick; t: number } | undefined;
    let glass: { pick: Pick; t: number } | undefined;
    for (const plate of this.layout.plates) {
      if (this.revealOf(plate.index) < 0.5) continue;
      if (this.focused !== null && this.focused !== plate.index) continue;

      const x = plate.x + (this.offsets[plate.index] ?? 0);
      const t = (x - origin.x) / direction.x;
      if (t <= 0) continue;

      const y = origin.y + direction.y * t;
      const z = origin.z + direction.z * t;
      if (Math.abs(y) > plate.height / 2 || Math.abs(z) > plate.width / 2)
        continue;

      if (!glass || t < glass.t)
        glass = { pick: { kind: "plate", plate: plate.index }, t };
      if (solid && solid.t <= t) continue;

      const panel = plate.panels.find(
        (candidate) =>
          Math.abs(z - candidate.u) <= candidate.width / 2 &&
          Math.abs(y - candidate.v) <= candidate.height / 2,
      );
      if (panel) {
        solid = {
          pick: { kind: "module", plate: plate.index, module: panel.module },
          t,
        };
        continue;
      }
      const grid = plate.experts;
      if (grid) {
        const pitch = grid.size + grid.gap;
        const left = -(grid.columns * pitch - grid.gap) / 2;
        const top = grid.v + (grid.rows * pitch - grid.gap) / 2;
        const column = Math.floor((z - left) / pitch);
        const row = Math.floor((top - y) / pitch);
        const expert = row * grid.columns + column;
        if (
          column >= 0 &&
          column < grid.columns &&
          row >= 0 &&
          expert < grid.count &&
          (z - left) % pitch <= grid.size &&
          (top - y) % pitch <= grid.size
        )
          solid = { pick: { kind: "expert", plate: plate.index, expert }, t };
      }
    }
    return solid?.pick ?? glass?.pick ?? null;
  }

  private setHover(pick: Pick | null) {
    const key = (value: Pick | null) =>
      !value
        ? ""
        : value.kind === "module"
          ? `m${value.module.index}`
          : value.kind === "expert"
            ? `e${value.plate}:${value.expert}`
            : `p${value.plate}`;
    if (key(pick) === key(this.hovered)) return;

    const panels = this.layout.panels;
    const previous = this.hovered;
    this.hovered = pick;
    if (previous?.kind === "module") {
      const instance = panels.findIndex(
        (panel) => panel.module.index === previous.module.index,
      );
      if (instance >= 0)
        this.panelState.setX(
          instance,
          previous.module.index === this.selected ? 2 : 0,
        );
    }
    if (pick?.kind === "module") {
      const instance = panels.findIndex(
        (panel) => panel.module.index === pick.module.index,
      );
      if (instance >= 0 && pick.module.index !== this.selected)
        this.panelState.setX(instance, 1);
    }
    this.panelState.needsUpdate = true;
    if (this.expertMaterial) {
      const owner = this.expertOwners.find(
        (entry) => pick?.kind === "expert" && entry.plate === pick.plate,
      );
      this.expertMaterial.uniforms.uHover!.value =
        owner && pick?.kind === "expert" ? owner.first + pick.expert : -1;
    }
    this.renderer.domElement.style.cursor = pick ? "pointer" : "grab";
    this.callbacks.hover(pick);
  }

  private bindPointer() {
    const canvas = this.renderer.domElement;
    canvas.style.cursor = "grab";
    const move = (event: PointerEvent) => {
      if (event.buttons) return;
      this.setHover(this.pick(event.clientX, event.clientY));
    };
    const down = (event: PointerEvent) => {
      this.pointerDown = { x: event.clientX, y: event.clientY };
    };
    const up = (event: PointerEvent) => {
      const start = this.pointerDown;
      this.pointerDown = undefined;
      if (
        !start ||
        Math.hypot(event.clientX - start.x, event.clientY - start.y) > 5
      )
        return;
      this.callbacks.select(this.pick(event.clientX, event.clientY));
    };
    const leave = () => this.setHover(null);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointerleave", leave);
    this.cleanups.push(() => {
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointerleave", leave);
    });
  }

  /** Keeps the scene centred in the area left of an overlay of this width. */
  setInset(pixels: number) {
    if (pixels === this.inset) return;

    this.inset = pixels;
    this.resize();
  }

  private resize() {
    const width = Math.max(this.container.clientWidth, 1);
    const height = Math.max(this.container.clientHeight, 1);
    const inset = Math.min(this.inset, width * 0.5);
    const top = this.headerInset(height);
    this.camera.aspect = width / height;
    // Centre the scene in the area left of the inspector and below the header.
    if (inset || top)
      this.camera.setViewOffset(
        width + inset,
        height + top,
        inset,
        0,
        width,
        height,
      );
    else this.camera.clearViewOffset();
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
    this.composer.setSize(width, height);
    this.bloom.resolution.set(width, height);
  }

  private plateX(s: number) {
    const plates = this.layout.plates;
    const clamped = THREE.MathUtils.clamp(s, 0, plates.length - 1.0001);
    const index = Math.floor(clamped);
    const f = clamped - index;
    const a = plates[index]!;
    const b = plates[index + 1] ?? a;
    return (
      THREE.MathUtils.lerp(a.x, b.x, f) + (s - clamped) * this.layout.spacing
    );
  }

  private updateTour(delta: number) {
    const tour = this.touring;
    if (!tour) return;

    const plates = this.layout.plates;
    const index = THREE.MathUtils.clamp(
      Math.round(tour.s),
      0,
      plates.length - 1,
    );
    const linger = 1 + 2.2 * (plates[index]?.intensity ?? 0);
    tour.s += (delta * Math.max(2.4, plates.length / 14)) / linger;
    const x = this.plateX(tour.s);
    const sway = Math.sin(tour.s * 0.35);
    this.camera.position.lerp(
      new THREE.Vector3(
        x - 3.2,
        this.layout.height * (0.3 + 0.08 * sway),
        this.layout.width * (0.78 + 0.1 * sway),
      ),
      1 - Math.exp(-delta * 3),
    );
    this.controls.target.lerp(
      new THREE.Vector3(x + 2.4, 0, 0),
      1 - Math.exp(-delta * 3),
    );
    if (tour.s >= plates.length - 1) {
      this.stopTour();
      this.callbacks.select({ kind: "plate", plate: plates.length - 1 });
    }
  }

  private readonly loop = (now: number) => {
    this.frame = requestAnimationFrame(this.loop);
    const delta = this.last ? Math.min((now - this.last) / 1000, 0.1) : 0;
    this.last = now;
    if (!this.reducedMotion) {
      this.time += delta;
      this.shared.uReveal!.value = Math.min(
        2,
        (now - this.revealStart - 300) / 2600,
      );
    }
    this.shared.uTime!.value = this.time;

    let moved = false;
    const ease = 1 - Math.exp(-delta * (this.reducedMotion ? 60 : 7));
    this.offsets.forEach((offset, index) => {
      const next = offset + ((this.targetOffsets[index] ?? 0) - offset) * ease;
      if (Math.abs(next - offset) > 1e-5) {
        this.offsets[index] = next;
        this.plateData[index * 4 + 1] = next;
        moved = true;
      }
    });
    if (moved) this.plateTexture.needsUpdate = true;
    const mix = this.shared.uFocusMix!.value as number;
    this.shared.uFocusMix!.value = mix + (this.focusTarget - mix) * ease;
    this.terrainUniforms.uGrow.value = Math.min(
      1,
      this.terrainUniforms.uGrow.value + delta * 1.4,
    );

    if (this.flight) {
      const flight = this.flight;
      const t = THREE.MathUtils.clamp(
        (now - flight.start) / flight.duration,
        0,
        1,
      );
      const eased = easeInOut(t);
      this.camera.position.lerpVectors(
        flight.fromPosition,
        flight.toPosition,
        eased,
      );
      this.controls.target.lerpVectors(
        flight.fromTarget,
        flight.toTarget,
        eased,
      );
      if (t >= 1) this.flight = undefined;
    }
    this.updateTour(delta);
    this.controls.update();
    this.composer.render(delta);
    this.updateLabels();
  };
}
