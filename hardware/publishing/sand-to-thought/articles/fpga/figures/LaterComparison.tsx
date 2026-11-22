import { FabricDiagram, FabricUsageChart, ModelDiagram } from "./MeasurementMechanism";
import { laterComparisons, type ComparisonScene } from "./laterComparisons";

export const LaterComparison = ({ scene }: { scene: ComparisonScene }) => {
  const comparison = laterComparisons[scene];
  return (
    <div className="fpga-measurement-mechanisms fpga-later-comparison">
      <div className="fpga-measurement-panel">
        <div className="fpga-measurement-panel-title">Generating a token</div>
        <ModelDiagram stages={comparison.stages} />
      </div>
      <div className="fpga-measurement-panel">
        <div className="fpga-measurement-panel-title">FPGA · {comparison.title}</div>
        <FabricDiagram
          resource={comparison.mapResource}
          externalMemory={comparison.ddr4WeightsKiB > 0}
          description={`FPGA diagram highlighting ${comparison.mapResource}.${comparison.ddr4WeightsKiB ? " External DDR4 supplies the weights." : ""} Before: ${comparison.before}. After: ${comparison.after}.`}
        >
          {comparison.mapResource === "Clock" ? (
            <g>
              {[20, 19].map((period, index) => (
                <g key={period} transform={`translate(38 ${108 + 41 * index})`}>
                  <text x="60" y="-11">{index === 0 ? comparison.before : comparison.after}</text>
                  <path
                    className="fpga-measurement-arrow"
                    data-active={index === 1}
                    d={`M0 7${`v-7h${period / 2}v7h${period / 2}`.repeat(6)}`}
                  />
                </g>
              ))}
            </g>
          ) : (
            <g className="fpga-comparison-change">
              <text x="98" y="95">Before</text>
              <text x="98" y="112">{comparison.before}</text>
              <text x="98" y="140">After</text>
              <text x="98" y="157">{comparison.after}</text>
            </g>
          )}
        </FabricDiagram>
      </div>
      <FabricUsageChart usage={comparison.resources} ddr4WeightsKiB={comparison.ddr4WeightsKiB} />
    </div>
  );
};
