import type { ReactElement } from "react";
import {
  Band,
  Features,
  Fold,
  Footer,
  Module,
  Nav,
  Substrate,
  TierExplorer,
} from "../components/design";
import { DocsModelCatalog } from "../components/docs/DocsModelCatalog";
import "../styles/index.css";

const FEATURES = [
  {
    title: "Pick the model.",
    body: "Run leading open models through one API. No provider hunt, new account, or integration for every model.",
  },
  {
    title: "Set the pace.",
    body: "Choose the latency your workload needs. Pay for that requirement instead of somebody else's idea of fast.",
  },
  {
    title: "Trust the endpoint.",
    body: "Get material savings from a reliable, SOC 2 provider with the technical depth to run production workloads.",
  },
];

export const InferencePage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed className="gr-module--fold" index={0}>
        <Fold
          title={["You set the pace.", "And the price."]}
          lede="Choose an open model, then set the latency your workload actually needs. We handle the infrastructure behind one API, so you get serious savings without giving up reliability, technical depth, or a provider you can trust."
        >
          <TierExplorer />
        </Fold>
      </Module>

      <Module index={1}>
        <Features
          action={{ href: "/docs/", label: "Read docs" }}
          items={FEATURES}
        />
      </Module>

      <Module index={2}>
        <h2 className="gr-heading gr-pair-title">Available models</h2>
        <p className="gr-body gr-muted" style={{ maxWidth: "none" }}>
          Move the tasks open models handle well to lower-cost inference, and
          keep frontier models for the work that needs them.
        </p>
        <DocsModelCatalog variant="site" />
        <p className="gr-body gr-muted">
          More models coming soon.{" "}
          <a
            className="underline underline-offset-4"
            href="mailto:team@gradiated.com?subject=Model%20request"
          >
            Request a model
          </a>
        </p>
      </Module>
    </Band>

    <Band>
      <Footer index={3} />
    </Band>
  </Substrate>
);
