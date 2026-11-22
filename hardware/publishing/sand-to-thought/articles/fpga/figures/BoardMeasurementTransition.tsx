import { Component, createRef, type ReactNode } from "react";

const boardScene = "board-request";
const measurementScene = "measuring-inference";

const chipOutline = {
  board: ".fpga-tour-chip .fpga-map-drawing > .fpga-chip-outline",
  measurement: ".fpga-measurement-map .fpga-chip-outline",
};

// Align the centre and height of each drawing's chip outline. The board layer
// uses CSS pixels, while the miniature map is inside a scaled SVG group.
function fitChip(anchor: DOMRect, target: DOMRect, x: number, y: number, unit: number) {
  const scale = target.height / anchor.height;
  const dx = target.x + target.width / 2 - x - scale * (anchor.x + anchor.width / 2 - x);
  const dy = target.y - y - scale * (anchor.y - y);
  return `translate(${dx / unit}px, ${dy / unit}px) scale(${scale})`;
}

type Props = { scene: string; smooth: boolean; children: ReactNode };

export class BoardMeasurementTransition extends Component<Props, {}, DOMRect | null> {
  private content = createRef<HTMLDivElement>();
  private animations: Animation[] = [];

  getSnapshotBeforeUpdate(previous: Props) {
    const { scene, smooth } = this.props;
    const forward = previous.scene === boardScene && scene === measurementScene;
    const backward = previous.scene === measurementScene && scene === boardScene;
    if ((!forward && !backward) || !smooth || matchMedia("(prefers-reduced-motion: reduce)").matches) return null;
    return this.content.current?.querySelector(forward ? chipOutline.board : chipOutline.measurement)?.getBoundingClientRect() ?? null;
  }

  private finish = () => {
    for (const animation of this.animations) {
      animation.onfinish = null;
      animation.cancel();
    }
    this.animations = [];
    this.content.current?.removeAttribute("data-board-transition");
  };

  componentWillUnmount() {
    this.finish();
  }

  componentDidUpdate(previous: Props, _state: unknown, start: DOMRect | null) {
    if (previous.scene === this.props.scene) return;
    this.finish();
    const content = this.content.current;
    if (!content || !start?.height) return;

    const board = content.querySelector<HTMLElement>("[data-board-layer]");
    const panels = content.querySelector<HTMLElement>("[data-measurement-layer]");
    const map = panels?.querySelector<SVGGElement>(".fpga-measurement-map");
    if (!board || !panels || !map) return;

    content.setAttribute("data-board-transition", "");
    const boardChip = board.querySelector(chipOutline.board)?.getBoundingClientRect();
    const smallChip = map.querySelector(".fpga-chip-outline")?.getBoundingClientRect();
    const matrix = map.getScreenCTM();
    if (!boardChip?.height || !smallChip?.height || !matrix?.a) {
      this.finish();
      return;
    }

    const forward = this.props.scene === measurementScene;
    const end = forward ? smallChip : boardChip;
    const origin = board.getBoundingClientRect();
    const timing = { duration: 620, easing: "cubic-bezier(.4,0,.2,1)", fill: "both" } as const;
    // Clear the board labels before revealing the experiment labels. Keep the
    // moving chip visible while its full drawing blends into the miniature.
    const fadeTiming = { ...timing, direction: forward ? "normal" : "reverse" } as const;
    const surroundings = board.querySelector(".fpga-board-world");
    this.animations = [
      board.animate([start, end].map(rect => ({
        transformOrigin: "0 0",
        transform: fitChip(boardChip, rect, origin.x, origin.y, 1),
      })), timing),
      map.animate([start, end].map(rect => ({
        transformOrigin: "0 0",
        transform: fitChip(smallChip, rect, matrix.e, matrix.f, matrix.a),
      })), timing),
      board.animate([{ opacity: 1 }, { opacity: 1, offset: 0.68 }, { opacity: 0 }], fadeTiming),
      panels.animate([{ opacity: 0 }, { opacity: 0, offset: 0.36 }, { opacity: 1 }], fadeTiming),
    ];
    if (surroundings) {
      this.animations.push(surroundings.animate([
        { opacity: 1 }, { opacity: 0, offset: 0.36 }, { opacity: 0 },
      ], fadeTiming));
    }
    this.animations[0].onfinish = this.finish;
  }

  render() {
    return <div className="fpga-figure-content" ref={this.content}>{this.props.children}</div>;
  }
}
