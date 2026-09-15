import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, ReactElement } from "react";
import {
  ARTWORK_SCATTERS,
  ARTWORK_SOURCES,
  artworkPresets,
} from "../lib/artwork";
import {
  recordCanvasToMP4,
  recordCanvasToWebM,
  WaferField,
  type EasingName,
  type ScatterPattern,
} from "../lib/wafer-field";
import { Band, Footer, Module, Nav, Substrate } from "../components/design";
import "../styles/index.css";

const download = (blob: Blob, filename: string) => {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
};

const Range = ({
  label,
  max,
  min,
  onChange,
  step = 1,
  value,
}: {
  label: string;
  max: number;
  min: number;
  onChange: (value: number) => void;
  step?: number;
  value: number;
}): ReactElement => (
  <label className="gr-art-control">
    <span>
      <span className="gr-label">{label}</span>
      <output>{value}</output>
    </span>
    <input
      max={max}
      min={min}
      onChange={(event) => onChange(Number(event.currentTarget.value))}
      step={step}
      type="range"
      value={value}
    />
  </label>
);

const EASINGS: Array<{ label: string; value: EasingName }> = [
  { label: "Ease out cubic", value: "easeOutCubic" },
  { label: "Ease out expo", value: "easeOutExpo" },
  { label: "Ease out back", value: "easeOutBack" },
  { label: "Ease out elastic", value: "easeOutElastic" },
  { label: "Linear", value: "linear" },
];

const LIBRARY_PRESETS = [
  ["carat", "Carat"],
  ["thesis", "Thesis"],
  ["mission", "Mission"],
  ["product", "Product"],
  ["sequencing", "Sequencing and depth"],
  ["people", "In person"],
  ["judgement", "What we look for"],
  ["gate", "Getting out the gate"],
  ["values", "Values"],
  ["brand", "Brand"],
] as const;

export const ArtworkGeneratorPage = (): ReactElement => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fieldRef = useRef<WaferField | null>(null);
  const [image, setImage] = useState<string>(artworkPresets.carat.source);
  const [columns, setColumns] = useState(144);
  const [chipSize, setChipSize] = useState(2);
  const [gap, setGap] = useState(1);
  const [cornerRadius, setCornerRadius] = useState(0);
  const [chipShape, setChipShape] = useState<"circle" | "square">("square");
  const [threshold, setThreshold] = useState(artworkPresets.carat.threshold);
  const [darkPixels, setDarkPixels] = useState(artworkPresets.carat.invert);
  const [palette, setPalette] = useState([...artworkPresets.carat.palette]);
  const [background, setBackground] = useState(artworkPresets.carat.background);
  const [backgroundTo, setBackgroundTo] = useState(
    artworkPresets.carat.backgroundTo,
  );
  const [scatter, setScatter] = useState<ScatterPattern>("orbit-in");
  const [duration, setDuration] = useState(900);
  const [stagger, setStagger] = useState(350);
  const [easing, setEasing] = useState<EasingName>("easeOutCubic");
  const [curve, setCurve] = useState(0.3);
  const [timingVariance, setTimingVariance] = useState(0.18);
  const [status, setStatus] = useState("Ready");

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let disposed = false;

    const field = new WaferField(canvas, {
      autoShimmer: false,
      bgColor: "transparent",
      chipColor: palette[0],
      chipSize,
      chipShape,
      cornerRadius,
      curveAmount: curve,
      depthAmount: 0.26,
      durationJitter: timingVariance,
      gap,
      pixelRatio: window.devicePixelRatio || 1,
      shading: "flat",
    });
    const paint = field.render.bind(field);
    const snapshot = document.createElement("canvas");
    field.render = () => {
      paint();
      const context = canvas.getContext("2d");
      const snapshotContext = snapshot.getContext("2d");
      if (
        !context ||
        !snapshotContext ||
        canvas.width === 0 ||
        canvas.height === 0
      )
        return field;
      if (
        snapshot.width !== canvas.width ||
        snapshot.height !== canvas.height
      ) {
        snapshot.width = canvas.width;
        snapshot.height = canvas.height;
      }
      snapshotContext.clearRect(0, 0, snapshot.width, snapshot.height);
      snapshotContext.drawImage(canvas, 0, 0);
      context.setTransform(1, 0, 0, 1, 0, 0);
      context.clearRect(0, 0, canvas.width, canvas.height);
      const gradient = context.createLinearGradient(
        0,
        canvas.height,
        canvas.width,
        0,
      );
      gradient.addColorStop(0, background);
      gradient.addColorStop(1, backgroundTo);
      context.fillStyle = gradient;
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(snapshot, 0, 0);
      return field;
    };
    fieldRef.current = field;

    const build = async () => {
      const rows = Math.max(12, Math.round(columns * 0.68));
      field.resize(columns, rows);
      await field.setShapeFromImage(image, {
        cols: columns,
        fill: true,
        fit: "cover",
        invert: darkPixels,
        mode: "luminance",
        palette,
        rows,
        threshold,
      });
      if (disposed) return;
      field.scatterIn(scatter).setProgress(1);
    };

    void build().catch(() => setStatus("That image could not be sampled."));
    return () => {
      disposed = true;
      field.stop();
      if (fieldRef.current === field) fieldRef.current = null;
    };
  }, [
    background,
    backgroundTo,
    chipShape,
    chipSize,
    columns,
    cornerRadius,
    curve,
    darkPixels,
    gap,
    image,
    palette,
    scatter,
    threshold,
    timingVariance,
  ]);

  const readImage = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setImage(String(reader.result));
      setStatus(file.name);
    };
    reader.readAsDataURL(file);
  };

  const assemble = () => {
    fieldRef.current
      ?.scatterIn(scatter)
      .assemble({ duration, easing, stagger });
  };

  const disperse = () => {
    fieldRef.current?.disperse({ duration, easing, pattern: scatter, stagger });
  };

  const exportPng = () => {
    const canvas = canvasRef.current;
    const field = fieldRef.current;
    if (!canvas || !field) return;
    const previousRatio = window.devicePixelRatio || 1;
    field.setPixelRatio(4);
    canvas.toBlob((blob) => {
      if (blob) download(blob, "gradiated-artwork.png");
      field.setPixelRatio(previousRatio);
    }, "image/png");
  };

  const record = async (format: "mp4" | "webm") => {
    const canvas = canvasRef.current;
    const field = fieldRef.current;
    if (!canvas || !field) return;
    setStatus(`Recording ${format.toUpperCase()}…`);
    try {
      const recorder =
        format === "mp4" ? recordCanvasToMP4 : recordCanvasToWebM;
      const blob = await recorder(canvas, {
        durationMs: duration + stagger + 250,
        fps: 60,
        onRecordingStarted: () => assemble(),
        videoBitsPerSecond: 16_000_000,
      });
      download(blob, `gradiated-artwork.${format}`);
      setStatus("Ready");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Recording failed.");
    }
  };

  return (
    <Substrate>
      <Nav />
      <Band>
        <Module className="gr-module--top gr-artwork-module" index={0}>
          <header className="gr-artwork-head">
            <div>
              <p className="gr-label">Tool</p>
              <h1 className="gr-masthead-title">Artwork generator</h1>
            </div>
            <p className="gr-lede gr-muted">
              Turn a photograph into a sharp, animated field of wafer dies.
            </p>
          </header>

          <div className="gr-artwork-app">
            <div className="gr-artwork-stage" style={{ background }}>
              <canvas
                aria-label="Generated wafer artwork"
                ref={canvasRef}
                role="img"
              />
            </div>

            <aside className="gr-artwork-panel">
              <div className="gr-art-section">
                <p className="gr-label">Source</p>
                <label className="gr-field">
                  <span className="gr-field-hint">Library preset</span>
                  <select
                    className="gr-select"
                    defaultValue=""
                    onChange={(event) => {
                      const preset = artworkPresets[event.currentTarget.value];
                      if (!preset) return;
                      setImage(preset.source);
                      setScatter(preset.scatter);
                      setThreshold(preset.threshold);
                      setDarkPixels(preset.invert);
                      setPalette([...preset.palette]);
                      setBackground(preset.background);
                      setBackgroundTo(preset.backgroundTo);
                    }}
                  >
                    <option disabled value="">
                      Choose a cover
                    </option>
                    {LIBRARY_PRESETS.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="gr-field">
                  <span className="gr-field-hint">Source photograph</span>
                  <select
                    className="gr-select"
                    onChange={(event) => setImage(event.currentTarget.value)}
                    value={
                      image.startsWith("/assets/artwork-sources/")
                        ? image
                        : "custom"
                    }
                  >
                    {!image.startsWith("/assets/artwork-sources/") ? (
                      <option value="custom">Uploaded image</option>
                    ) : null}
                    {ARTWORK_SOURCES.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="gr-art-upload">
                  <span>Use an image</span>
                  <input accept="image/*" onChange={readImage} type="file" />
                </label>
              </div>

              <div className="gr-art-section">
                <p className="gr-label">Block palette</p>
                <div className="gr-art-palette">
                  {palette.map((colour, index) => (
                    <label key={index}>
                      <span className="gr-field-hint">{index + 1}</span>
                      <input
                        aria-label={`Block colour ${index + 1}`}
                        onChange={(event) =>
                          setPalette((current) =>
                            current.map((entry, entryIndex) =>
                              entryIndex === index
                                ? event.currentTarget.value
                                : entry,
                            ),
                          )
                        }
                        type="color"
                        value={colour}
                      />
                    </label>
                  ))}
                </div>
              </div>

              <div className="gr-art-section gr-art-pair">
                <label>
                  <span className="gr-label">Gradient start</span>
                  <input
                    onChange={(event) =>
                      setBackground(event.currentTarget.value)
                    }
                    type="color"
                    value={background}
                  />
                </label>
                <label>
                  <span className="gr-label">Gradient end</span>
                  <input
                    onChange={(event) =>
                      setBackgroundTo(event.currentTarget.value)
                    }
                    type="color"
                    value={backgroundTo}
                  />
                </label>
              </div>

              <div className="gr-art-section">
                <Range
                  label="Grid resolution"
                  max={220}
                  min={48}
                  onChange={setColumns}
                  value={columns}
                />
                <Range
                  label="Chip size"
                  max={8}
                  min={1}
                  onChange={setChipSize}
                  value={chipSize}
                />
                <Range
                  label="Gap"
                  max={4}
                  min={0}
                  onChange={setGap}
                  value={gap}
                />
                <Range
                  label="Corner radius"
                  max={chipSize / 2}
                  min={0}
                  onChange={setCornerRadius}
                  step={0.5}
                  value={Math.min(cornerRadius, chipSize / 2)}
                />
                <div
                  className="gr-art-style"
                  role="group"
                  aria-label="Chip style"
                >
                  <button
                    aria-pressed={chipShape === "square" && cornerRadius === 0}
                    onClick={() => {
                      setChipShape("square");
                      setCornerRadius(0);
                    }}
                    type="button"
                  >
                    Sharp
                  </button>
                  <button
                    aria-pressed={chipShape === "square" && cornerRadius > 0}
                    onClick={() => {
                      setChipShape("square");
                      setCornerRadius(Math.max(1, chipSize / 4));
                    }}
                    type="button"
                  >
                    Rounded
                  </button>
                  <button
                    aria-pressed={chipShape === "circle"}
                    onClick={() => setChipShape("circle")}
                    type="button"
                  >
                    Circle
                  </button>
                </div>
              </div>

              <div className="gr-art-section">
                <Range
                  label="Tone balance"
                  max={255}
                  min={0}
                  onChange={setThreshold}
                  value={threshold}
                />
                <label className="gr-art-check">
                  <input
                    checked={darkPixels}
                    onChange={(event) =>
                      setDarkPixels(event.currentTarget.checked)
                    }
                    type="checkbox"
                  />
                  <span>Dark pixels become chips</span>
                </label>
              </div>

              <div className="gr-art-section">
                <label className="gr-field">
                  <span className="gr-field-hint">Scatter pattern</span>
                  <select
                    className="gr-select"
                    onChange={(event) =>
                      setScatter(event.currentTarget.value as ScatterPattern)
                    }
                    value={scatter}
                  >
                    {ARTWORK_SCATTERS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="gr-field">
                  <span className="gr-field-hint">Easing</span>
                  <select
                    className="gr-select"
                    onChange={(event) =>
                      setEasing(event.currentTarget.value as EasingName)
                    }
                    value={easing}
                  >
                    {EASINGS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <Range
                  label="Duration"
                  max={2400}
                  min={200}
                  onChange={setDuration}
                  step={50}
                  value={duration}
                />
                <Range
                  label="Stagger"
                  max={1200}
                  min={0}
                  onChange={setStagger}
                  step={25}
                  value={stagger}
                />
                <Range
                  label="Path curve"
                  max={0.9}
                  min={0}
                  onChange={setCurve}
                  step={0.05}
                  value={curve}
                />
                <Range
                  label="Timing variance"
                  max={0.8}
                  min={0}
                  onChange={setTimingVariance}
                  step={0.05}
                  value={timingVariance}
                />
              </div>

              <div className="gr-art-section gr-art-actions">
                <button
                  className="gr-art-primary"
                  onClick={assemble}
                  type="button"
                >
                  Assemble
                </button>
                <button onClick={disperse} type="button">
                  Disperse
                </button>
              </div>

              <div className="gr-art-section gr-art-exports">
                <p className="gr-label">Export</p>
                <button onClick={exportPng} type="button">
                  PNG · 4×
                </button>
                <button onClick={() => void record("webm")} type="button">
                  WebM
                </button>
                <button onClick={() => void record("mp4")} type="button">
                  MP4
                </button>
                <p aria-live="polite" className="gr-field-hint">
                  {status}
                </p>
              </div>
            </aside>
          </div>
        </Module>
      </Band>
      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
