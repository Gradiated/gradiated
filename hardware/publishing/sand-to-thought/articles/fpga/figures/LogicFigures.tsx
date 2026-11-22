import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { FigureSlot } from "./FigureSlot";
import {
  configurationScenes,
  continuationBounds,
  continuationFor,
  continuationTransform,
  hasNeuronReference,
  isLaterScene,
  ContinuationContents,
  ContinuationControls,
  useContinuation,
} from "./ChipContinuation";
import { lookup } from "./model";
import { Figure, Label } from "./drawing";
import { ChipMap } from "./ChipMap";
import { ResourceColumnLegend } from "./ResourceColumns";
import { openingViewFor } from "./opening";
import { NetworkIntro, networkIntroScenes } from "./NetworkIntro";
import {
  ArchitectureContents,
  ArchitectureControls,
  ArchitectureLocation,
  architectureTitle,
  architectureTransform,
  useArchitecture,
  useOutgoingArchitecture,
} from "./ArchitectureTour";
import {
  applicationFor,
  applicationTitles,
  useApplicationMotion,
  CernEnvironment,
  DisplayEnvironment,
  PrototypeEnvironment,
  ApplicationCircuit,
} from "./ApplicationEnvironments";

type Detail = {
  scene: string;
  key: string;
  content: ReactNode;
  bounds?: (typeof continuationBounds)[keyof typeof continuationBounds];
};

const DetailLayer = ({
  detail,
  parent,
  chipTarget,
  active,
  zoomOut,
}: {
  detail: Detail;
  parent: SVGGElement | null;
  chipTarget: SVGGElement | null;
  active: boolean;
  zoomOut: boolean;
}) => {
  const [target, setTarget] = useState<SVGGElement | null>(null);
  const { bounds } = detail;

  return (
    <>
      {parent &&
        createPortal(
          <g
            ref={setTarget}
            className="fpga-tour-layer fpga-detail-layer"
            data-visible={active}
            data-detail-scene={detail.scene}
            data-continuous={isLaterScene(detail.scene) || undefined}
            data-zoom-out={zoomOut}
            aria-hidden={!active}
            transform={
              bounds
                ? `translate(${bounds[0]} ${bounds[1]}) scale(${bounds[2] / 560})`
                : undefined
            }
          />,
          parent,
        )}
      <FigureSlot.Provider value={{ target, chipTarget, active }}>
        <div className="fpga-detail-controls" hidden={!active}>
          {detail.content}
        </div>
      </FigureSlot.Provider>
    </>
  );
};

export const ReconfigureFigure = ({
  scene,
  detail,
}: {
  scene: string;
  detail?: ReactNode;
}) => {
  const continuation = continuationFor(scene);
  const networkIntro = (networkIntroScenes as readonly string[]).includes(
    scene,
  );
  const neuronReference = hasNeuronReference(scene);
  const state = useContinuation(scene);
  const later = isLaterScene(scene);
  const [chipTarget, setChipTarget] = useState<SVGGElement | null>(null);
  const [worldTarget, setWorldTarget] = useState<SVGGElement | null>(null);
  const [detailTarget, setDetailTarget] = useState<SVGGElement | null>(null);
  const bounds =
    continuation && continuation.focus !== "chip"
      ? continuationBounds[continuation.focus]
      : undefined;
  const currentDetail: Detail | undefined =
    detail === undefined || detail === null || networkIntro
      ? undefined
      : {
          scene,
          key: continuation?.detail ? continuation.focus : "world",
          content: detail,
          bounds,
        };
  const [previousDetail, setPreviousDetail] = useState(currentDetail);
  const [outgoingDetail, setOutgoingDetail] = useState<Detail>();

  if (currentDetail?.scene !== previousDetail?.scene) {
    setPreviousDetail(currentDetail);
    setOutgoingDetail(
      previousDetail?.key !== currentDetail?.key ? previousDetail : undefined,
    );
  }

  const outgoingBounds = outgoingDetail?.bounds;
  const zoomingOut = Boolean(
    outgoingBounds && (!bounds || outgoingBounds[2] < bounds[2]),
  );

  useEffect(() => {
    if (!outgoingDetail) return;

    const timeout = window.setTimeout(
      () => setOutgoingDetail(undefined),
      zoomingOut ? 650 : 240,
    );
    return () => window.clearTimeout(timeout);
  }, [outgoingDetail, zoomingOut]);

  const detailLayers = [outgoingDetail, currentDetail];
  const application = applicationFor(scene);
  const tour = useArchitecture(scene);
  const outgoingTour = useOutgoingArchitecture(tour);
  const view =
    application || tour.view || continuation
      ? undefined
      : openingViewFor(scene);
  const circuit = view && "rule" in view ? view : undefined;
  const loadingOverview = (configurationScenes as readonly string[]).includes(
    scene,
  );
  const routing = scene.startsWith("routing-") || loadingOverview;
  const motion = useApplicationMotion();

  return (
    <div
      ref={motion.host}
      className="fpga-application-tour"
      data-application={application ?? "none"}
      data-continuous={later || undefined}
      data-world={continuation?.world || undefined}
      data-network-intro={networkIntro || undefined}
      data-neuron-reference={neuronReference || undefined}
      data-running={motion.running}
      data-configuration={loadingOverview ? scene : undefined}
      data-resource-columns={continuation?.columns || undefined}
      data-view={
        continuation
          ? continuation.detail
            ? "detail"
            : continuation.expanded
              ? "expanded-chip"
              : "chip"
          : (tour.view ?? "opening")
      }
    >
      {continuation ? (
        continuation.location && (
          <p className="fpga-tour-location">{continuation.location}</p>
        )
      ) : (
        <ArchitectureLocation scene={scene} />
      )}
      <Figure
        viewBox={
          scene === "our-board" || scene === "board-request"
            ? "-40 -6 640 542"
            : "-40 24 640 512"
        }
        title={
          application
            ? applicationTitles[application]
            : (continuation?.title ?? architectureTitle(scene) ?? view!.title)
        }
      >
        <ResourceColumnLegend visible={Boolean(continuation?.columns)} />
        <g
          className="fpga-application-environment"
          data-active={application === "cern"}
          aria-hidden={application !== "cern"}
        >
          <CernEnvironment />
        </g>
        <g
          className="fpga-application-environment"
          data-active={application === "prototype"}
          aria-hidden={application !== "prototype"}
        >
          <PrototypeEnvironment />
        </g>
        <g
          className="fpga-tour-chip"
          style={{
            transform: continuation
              ? continuationTransform(continuation)
              : architectureTransform(tour.view, Boolean(application)),
          }}
        >
          <g
            className="fpga-tour-layer"
            data-visible={
              continuation
                ? !continuation.detail
                : !tour.view || tour.view === "chip"
            }
            data-context={Boolean(
              continuation?.detail ||
              (tour.view && tour.view !== "chip" && tour.view !== "cell"),
            )}
            aria-hidden={Boolean(tour.view && tour.view !== "chip")}
          >
            <ChipMap
              hideVerticalConnectionsFor={tour.view === "clb" ? 1 : undefined}
              blockVerticalInsets={
                tour.view === "clb-overview"
                  ? { 1: [(80 * 72) / 560, (40 * 72) / 560] }
                  : undefined
              }
              expanded={continuation?.expanded}
              columns={continuation?.columns}
              blockDetails={
                continuation
                  ? scene === "neuron-hardware"
                    ? { 2: "Control" }
                    : ["map-and-route", "running-parameters"].includes(scene)
                      ? { 1: "Count", 5: "Logic", 9: "Output" }
                      : ["neuron-map", "token-journey"].includes(scene)
                        ? { 2: "State", 5: "Control" }
                        : scene === "memory-roles"
                          ? { 1: "Settings", 2: "Working state" }
                          : undefined
                  : undefined
              }
              focus={routing ? "junction" : "block"}
              source={
                loadingOverview
                  ? ["configuration-distribute", "configuration-luts"].includes(
                      scene,
                    )
                    ? 1
                    : 4
                  : tour.route === 0
                    ? 1
                    : 4
              }
              selectedBlocks={scene === "inside-chip" ? [1] : undefined}
              highlight={
                view && "highlight" in view
                  ? view.highlight
                  : (continuation && !loadingOverview) ||
                      application ||
                      (tour.view && !routing)
                    ? "blank"
                    : undefined
              }
              rule={circuit ? `(${circuit.rule})` : undefined}
              inputs={circuit?.inputs}
              output={
                circuit ? lookup(circuit.rule, ...circuit.inputs) : undefined
              }
            />
          </g>
          {application && <ApplicationCircuit application={application} />}
          <g
            className="fpga-tour-layer"
            data-visible={!continuation || Boolean(outgoingTour)}
            aria-hidden={Boolean(continuation)}
          >
            <ArchitectureContents tour={tour} outgoing={outgoingTour} />
          </g>
          <g
            className="fpga-tour-layer"
            data-visible={Boolean(continuation && !continuation.detail)}
            data-context={continuation?.detail}
            aria-hidden={Boolean(continuation?.detail)}
          >
            <ContinuationContents scene={scene} state={state} />
          </g>
          <g ref={setDetailTarget} />
          <g ref={setChipTarget} />
        </g>
        <g
          className="fpga-application-environment"
          data-active={application === "display"}
          aria-hidden={application !== "display"}
        >
          <DisplayEnvironment />
        </g>
        <g ref={setWorldTarget} />
        <Label x={280} y={179} className="fpga-app-chip-name">
          {application === "prototype" ? "FPGA prototype board" : "FPGA"}
        </Label>
      </Figure>
      <ArchitectureControls tour={tour} />
      <ContinuationControls scene={scene} state={state} />
      {(networkIntro || neuronReference) && (
        <FigureSlot.Provider value={{ target: worldTarget, chipTarget }}>
          <NetworkIntro scene={scene} />
        </FigureSlot.Provider>
      )}
      {detailLayers.map(
        (layer) =>
          layer && (
            <DetailLayer
              key={layer.key}
              detail={layer}
              parent={layer.bounds ? detailTarget : worldTarget}
              chipTarget={chipTarget}
              active={layer === currentDetail}
              zoomOut={layer === outgoingDetail && zoomingOut}
            />
          ),
      )}
    </div>
  );
};
