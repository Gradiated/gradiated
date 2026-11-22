import throughputChart from "./assets/illustrative-throughput.svg";
import boardPhoto from "./assets/kv260-board.jpg";
import { chipChoiceIcons } from "../../shared/figures/ChipChoiceIcons";
import { InferenceProfileChart } from "../../shared/figures/InferenceProfile";

const chipChoices = [
  {
    name: "FPGA",
    icon: chipChoiceIcons.FPGA,
    pros: [
      "Process large streams of data in parallel",
      "Respond quickly and predictably",
      "Extremely customisable?",
    ],
    cons: [
      "Takes time to design and verify?",
      "Limited on-chip logic and memory",
      "Throughput can be limited by memory bandwidth",
      "Customisability adds space and energy overhead",
    ],
  },
  {
    name: "CPU",
    icon: chipChoiceIcons.CPU,
    pros: [
      "Runs varied software with mature tools",
      "Good at work with lots of decisions",
    ],
    cons: ["Lower throughput for parallel maths"],
  },
  {
    name: "GPU",
    icon: chipChoiceIcons.GPU,
    pros: [
      "Fast large batches of matrix multiplies",
      "Optimised libraries for AI and graphics",
    ],
    cons: [
      "Small jobs can leave units idle",
      "Transfer bandwidth issues",
    ],
  },
  {
    name: "ASIC",
    icon: chipChoiceIcons.ASIC,
    pros: [
      "Fast, energy-efficient for a specific job",
      "Can cost less per chip at high volume",
    ],
    cons: [
      "High upfront cost + development time",
      "Changing circuitry means new chip",
    ],
  },
] as const;

export const ChipChoicesSlide = () => (
  <div className="fpga-lecture-closing fpga-lecture-chip-choices">
    <table>
      <thead>
        <tr>
          <th scope="col">Chip</th>
          <th scope="col">Pros</th>
          <th scope="col">Cons</th>
        </tr>
      </thead>
      <tbody>
        {chipChoices.map(({ name, icon: Icon, pros, cons }) => (
          <tr key={name}>
            <th scope="row">
              <span>
                <Icon aria-hidden="true" strokeWidth={1.6} />
                {name}
              </span>
            </th>
            {[pros, cons].map((points) => (
              <td key={points[0]}>
                <ul>
                  {points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

export const InferenceComparisonSlide = () => (
  <div className="fpga-lecture-closing fpga-lecture-comparison">
    <ul className="fpga-lecture-points">
      <li>
        <strong>Try more designs on the same board.</strong>
      </li>
      <li>
        <strong>Change one thing at a time.</strong>
      </li>
      <li>
        <strong>Find what limits the next improvement.</strong>
      </li>
      <li>
        <strong>How does AI help?</strong>
      </li>
    </ul>
    <p className="fpga-lecture-api-callout">We can offer this one on the API</p>

    <figure>
      <img
        src={throughputChart}
        alt="Example trends over successive experiments. Tokens per second rise throughout. Cost per token rises as more work moves to the FPGA, falls when model weights and the KV cache move to distributed RAM, and rises when more multiply-adds run in parallel. A gold arrow points to the final blue point."
      />
    </figure>
  </div>
);

const exampleProfiles = [
  {
    device: "NVIDIA H100",
    scores: {
      cost: 0.48,
      throughput: 0.9,
      latency: 0.65,
      capacity: 0.9,
      bandwidth: 0.95,
      energy: 0.58,
    },
  },
  {
    device: "Google v5e",
    scores: {
      cost: 0.68,
      throughput: 0.86,
      latency: 0.52,
      capacity: 0.76,
      bandwidth: 0.82,
      energy: 0.9,
    },
  },
  {
    device: "AMD EPYC 9654",
    scores: {
      cost: 0.58,
      throughput: 0.3,
      latency: 0.7,
      capacity: 0.73,
      bandwidth: 0.37,
      energy: 0.4,
    },
  },
  {
    device: "Apple M2",
    scores: {
      cost: 0.76,
      throughput: 0.52,
      latency: 0.82,
      capacity: 0.48,
      bandwidth: 0.55,
      energy: 0.77,
    },
  },
  {
    device: "AMD Instinct MI300X",
    scores: {
      cost: 0.55,
      throughput: 0.81,
      latency: 0.43,
      capacity: 0.95,
      bandwidth: 0.88,
      energy: 0.61,
    },
  },
] as const;

export const InferenceExperimentSlide = () => (
  <div className="fpga-lecture-closing fpga-lecture-experiment">
    <div className="fpga-lecture-experiment-board">
      <img
        src={boardPhoto}
        alt="AMD Kria KV260 starter board with its fan and ports"
        width="640"
        height="640"
      />
      <div className="fpga-lecture-experiment-copy">
        <p className="fpga-lecture-experiment-goal">
          How low can we get the cost per token while keeping the answers the
          same and the replies just as fast?
        </p>
        <ul className="fpga-lecture-points">
          <li>
            Fit the largest model we can on the KV260 and run it as fast as
            possible.
          </li>
          <li>
            <strong>Two standard benchmarks:</strong> speed on a small model
            and energy per token on a larger model.
          </li>
        </ul>
        <p className="fpga-lecture-experiment-method">
          Repeat each test with the same model, prompts, token limits and
          quality target.
        </p>
        <p className="fpga-lecture-experiment-next">
          <strong>Next: measured results from this board</strong>
        </p>
      </div>
    </div>

    <section className="fpga-lecture-experiment-profiles" aria-label="Example chip profiles">
      <div>
        {exampleProfiles.map(({ device, scores }) => (
          <div key={device}>
            <h2>{device}</h2>
            <InferenceProfileChart
              device={device}
              illustrativeScores={scores}
              compact
            />
          </div>
        ))}
      </div>
    </section>
  </div>
);
