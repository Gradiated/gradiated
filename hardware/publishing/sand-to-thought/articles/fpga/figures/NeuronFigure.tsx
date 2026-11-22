import { useContext, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { FigureSlot } from "./FigureSlot";
import { useApplicationMotion } from "./ApplicationEnvironments";
import { DspDatapath } from "./DspDatapath";
import { Figure, Label } from "./drawing";

export const NeuronFigure = ({ scene }: { scene: string }) => {
  const second = scene === "neuron-next";
  const active = useContext(FigureSlot)?.active !== false;
  const motion = useApplicationMotion();
  const [beat, setBeat] = useState(0);
  const [reduced, setReduced] = useState(false);
  const progress = useRef(0);

  useEffect(() => {
    if (!active) return;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let timer: number | undefined;
    const stages = [1100, 2200, 3200, 3900, 5100];
    const start = () => {
      window.clearInterval(timer);
      setReduced(media.matches);
      if (media.matches) {
        progress.current = stages.at(-1)!;
        setBeat(5);
        return;
      }
      if (!motion.running || progress.current >= stages.at(-1)!) return;

      let previous = performance.now();
      timer = window.setInterval(() => {
        const now = performance.now();
        progress.current += now - previous;
        previous = now;
        setBeat(stages.filter((time) => time <= progress.current).length);
        if (progress.current >= stages.at(-1)!) window.clearInterval(timer);
      }, 50);
    };
    start();
    media.addEventListener("change", start);
    return () => {
      window.clearInterval(timer);
      media.removeEventListener("change", start);
    };
  }, [active, motion.running]);

  const input = second ? 2 : 3;
  const weight = second ? -1 : 2;
  const product = input * weight;
  const before = second ? 6 : 0;
  const after = before + product;
  const saved = beat >= 3;
  const travelling = beat === 1 || beat === 2 || beat === 4;

  return (
    <>
      <div ref={motion.host} />
      <Figure
        viewBox="0 0 560 370"
        title={`The same DSP ${second ? "subtracts the second product" : "adds the first product"}. ${input} times ${weight} is ${product}. The clock saves ${after} in the running-total register.`}
      >
        <g
          className="fpga-resource-circuit fpga-dsp-demo fpga-neuron-demo"
          data-saved={saved}
        >
          <Label x={65} y={62} small>
            Input
          </Label>
          <Label x={65} y={162} small>
            Weight
          </Label>
          <DspDatapath
            input={input}
            weight={weight}
            total={saved ? after : before}
            accumulate
            pending={!saved}
            showSavedTotalLabel={false}
            clockTriggered={beat === 3 && !reduced}
            flows={
              reduced
                ? {}
                : {
                    inputs:
                      beat === 0 && motion.running
                        ? { duration: 850, delay: 180 }
                        : undefined,
                    product: beat === 1 ? { duration: 850 } : undefined,
                    sum: beat === 2 ? { duration: 850 } : undefined,
                    clock: beat === 2 ? { duration: 850 } : undefined,
                    feedback: beat === 4 ? { duration: 1100 } : undefined,
                  }
            }
          />
          <g className="fpga-dsp-demo-values">
            <Label
              x={65}
              y={102}
              value
              className={saved ? "fpga-faint" : undefined}
            >
              {input}
            </Label>
            <Label
              x={65}
              y={202}
              value
              className={saved ? "fpga-faint" : undefined}
            >
              {weight < 0 ? `−${-weight}` : weight}
            </Label>
            <Label x={275} y={146} value>
              {beat === 2 ? (product < 0 ? `−${-product}` : product) : ""}
            </Label>
            <Label x={459} y={80} small>
              Running
            </Label>
            <Label x={459} y={112} small>
              total
            </Label>
            <Label x={459} y={180} value className="fpga-dsp-register-value">
              {saved ? after : before}
            </Label>
            <Label x={300} y={240} value>
              {beat >= 5 ? after : before}
            </Label>
          </g>
          {travelling && !reduced && (
            <g
              key={beat}
              className="fpga-dsp-moving-number"
              style={
                {
                  offsetPath: `path("${beat === 1 ? "M248 180H303" : beat === 2 ? "M363 180H459" : "M510 180H540V285H333V240"}")`,
                  animationDuration: beat === 4 ? "1100ms" : "850ms",
                } as CSSProperties
              }
            >
              <g className="fpga-dsp-number">
                <circle r={19} />
                <Label x={0} y={0} value>
                  {beat === 1
                    ? product < 0
                      ? `−${-product}`
                      : product
                    : after}
                </Label>
              </g>
            </g>
          )}
        </g>
      </Figure>
    </>
  );
};
