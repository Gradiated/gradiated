import { steps } from "./sequence";
import article from "../../../../content/articles/fabricating-a-transistor/script.md?fabrication-article";

export const machines = [
  {
    id: "furnace",
    label: "Oxidation furnace",
    job: "Grow oxide by reacting silicon with oxygen",
    wiki: "Thermal_oxidation",
    summary:
      "Thermal oxidation forms silicon dioxide by reacting silicon with oxygen-containing gases at elevated temperature. Growing the oxide consumes some of the silicon beneath it.",
  },
  {
    id: "coat",
    label: "Coater",
    job: "Spread a temporary resist film",
    wiki: "Spin_coating",
    summary:
      "Spin coating spreads a liquid over a rotating surface to form a thin film. Here it coats the wafer with light-sensitive photoresist.",
  },
  {
    id: "litho",
    label: "Lithography",
    job: "Expose a pattern in photoresist",
    wiki: 'Photolithography#Exposure_("printing")_systems',
    summary:
      "Photolithography uses light to define a pattern in a sensitive coating. Development then creates openings used by subsequent fabrication operations.",
  },
  {
    id: "develop",
    label: "Developer",
    job: "Remove the exposed positive resist",
    wiki: "Photolithography#Exposure_and_developing",
    summary:
      "Developer dissolves the light-exposed areas of our positive resist. The unexposed resist stays on the wafer as a protective pattern. This bench uses different chemistry from the resist stripper.",
  },
  {
    id: "etch",
    label: "Etcher",
    job: "Remove selected material",
    wiki: "Reactive-ion_etching",
    summary:
      "Reactive-ion etching combines chemical reactions and ion bombardment to remove exposed material. Oxide, polysilicon and metal need different etch processes. This symbol represents a family of tools.",
  },
  {
    id: "strip",
    label: "Resist stripper",
    job: "Remove the remaining protective resist",
    wiki: "Photolithography#Photoresist_removal",
    summary:
      "After etching or implantation, a resist remover strips away the remaining protective coating. Unlike development, this operation removes the resist pattern once its job is finished.",
  },
  {
    id: "anneal",
    label: "Annealer",
    job: "Repair implantation damage and activate dopants",
    wiki: "Rapid_thermal_processing#Rapid_thermal_anneal",
    summary:
      "Annealing heats implanted silicon to repair crystal damage and make dopants electrically active. This is a separate heat treatment from growing an oxide film.",
  },
  {
    id: "implant",
    label: "Implanter",
    job: "Introduce dopants into silicon",
    wiki: "Ion_implantation",
    summary:
      "Ion implantation accelerates ions into a solid. In semiconductor fabrication it can introduce dopants into selected regions of a wafer.",
  },
  {
    id: "deposit",
    label: "Film deposition",
    job: "Deposit nitride, polysilicon or insulation",
    wiki: "Chemical_vapor_deposition",
    summary:
      "Chemical vapour deposition forms a film through chemical reactions at the wafer. We use this equipment category for silicon nitride, polysilicon and oxide films, with a different process for each material. Metal deposition has its own station.",
  },
  {
    id: "metal",
    label: "Metal deposition",
    job: "Add conducting material for contacts and wires",
    wiki: "Sputter_deposition",
    summary:
      "Metal deposition adds conducting material for connections. Physical vapour deposition is one way to deposit aluminium films. Our drawing simplifies the filling of contact holes and vias.",
  },
  {
    id: "polish",
    label: "Polisher",
    job: "Flatten the surface",
    wiki: "Chemical-mechanical_polishing",
    summary:
      "Chemical-mechanical polishing combines chemical action with mechanical abrasion to remove material and reduce surface height differences.",
  },
  {
    id: "inspect",
    label: "Inspection",
    job: "Check patterns and connections",
    wiki: "Semiconductor_device_fabrication#Wafer_metrology",
    summary:
      "Measurements, inspection and electrical tests help manufacturers check the structures they are producing. They recur throughout fabrication.",
  },
] as const;

export type MachineId = (typeof machines)[number]["id"];

export { steps } from "./sequence";

if (article.scenes.length !== steps.length)
  throw new Error("Fabrication script and sequence differ in length");
export const introduction = article.introduction;
export const bibliography = article.bibliography;
export const scenes = steps.map((step, index) => {
  if (article.scenes[index].key !== step.key) {
    throw new Error(`Fabrication scene ${step.key} is missing from script.md`);
  }

  return {
    ...step,
    html: article.scenes[index].html,
  };
});

export const groups = scenes.filter(
  (step, index) => index === 0 || step.group !== scenes[index - 1].group,
);
export const visitedMachines = (index: number): MachineId[] =>
  machines
    .filter((machine) =>
      steps.slice(0, index + 1).some((step) => step.machine === machine.id),
    )
    .map((machine) => machine.id);
