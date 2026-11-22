import {
  experimentNumbers,
  experimentPosition,
} from "../../articles/fpga/figures/MeasurementChart";

const groups = [
  {
    label: "Skip work",
    description: "Avoid a CPU round trip, unused scores or division steps with a known answer",
    runs: [["1", "2"], ["8"], ["11"], ["18"]],
  },
  {
    label: "More work per tick",
    description: "Handle more digits per tick, calculate side by side or fetch the next data while calculating",
    runs: [
      ["3", "4", "5", "6a", "6b", "7"],
      ["9", "10"],
      ["13"],
      ["17"],
      ["19", "20"],
      ["22", "23"],
    ],
  },
  {
    label: "Weight storage and reads",
    description: "Change where weights are stored or how they are fetched",
    runs: [["12"], ["14", "15", "16"]],
  },
  {
    label: "Share hardware",
    description: "Three normalisation stages take turns using one multiplier",
    runs: [["21"]],
  },
  {
    label: "Faster clock",
    description: "Run the circuit on a faster clock",
    runs: [["24"]],
  },
];

export function ExperimentGroups({ step }: { step: number }) {
  const current = experimentNumbers[step];
  const currentRow = groups.findIndex((group) =>
    group.runs.some((run) => run.includes(current)),
  );
  return (
    <ul
      className="lecture-experiment-groups"
      aria-label="Experiments grouped by type of improvement"
    >
      {groups.map(({ label, description, runs }, row) => {
        const numbers = runs.flat();
        const last = experimentPosition(
          experimentNumbers.indexOf(numbers[numbers.length - 1]),
        );
        const summary = `${description}. Experiment${numbers.length === 1 ? "" : "s"} ${numbers.join(", ")}.`;
        return (
          <li key={label} data-current={row === currentRow} title={summary}>
            <span className="lecture-group-track" aria-hidden="true">
              {row <= currentRow && (
                <i
                  className="lecture-group-guide"
                  style={{ left: experimentPosition(step) }}
                />
              )}
              <i className="lecture-group-leader" style={{ left: last }} />
              {runs.map((run) => {
                const first = experimentPosition(
                  experimentNumbers.indexOf(run[0]),
                );
                const end = experimentPosition(
                  experimentNumbers.indexOf(run[run.length - 1]),
                );
                return (
                  <span
                    key={run[0]}
                    className="lecture-group-run"
                    style={{ left: first, right: `calc(100% - ${end})` }}
                  >
                    {run.map((n, i) => (
                      <i
                        key={n}
                        data-selected={n === current}
                        style={{
                          left:
                            run.length === 1
                              ? 0
                              : `${(100 * i) / (run.length - 1)}%`,
                        }}
                      />
                    ))}
                  </span>
                );
              })}
            </span>
            <span className="lecture-group-name" aria-hidden="true">
              {label}
            </span>
            <span className="fpga-measurements-sr">
              {summary}
              {row === currentRow && " Current category."}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
