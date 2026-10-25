import type { MachineId } from "./model";

export type MaskId =
  | "well"
  | "isolation"
  | "gate"
  | "n"
  | "p"
  | "contact"
  | "metal"
  | "via"
  | "upper";
export type MaskPhase = "coat" | "expose" | "develop" | "operate" | "strip";
export type FabricationStep = {
  key: string;
  title: string;
  operation: string;
  machine?: MachineId;
  group: number;
  mask?: MaskId;
  phase?: MaskPhase;
};

export const maskDefinitions: {
  id: MaskId;
  label: string;
  operation: "Implant" | "Etch";
}[] = [
  { id: "well", label: "N-well", operation: "Implant" },
  { id: "isolation", label: "Device sites", operation: "Etch" },
  { id: "gate", label: "Gates", operation: "Etch" },
  { id: "n", label: "N-type implant", operation: "Implant" },
  { id: "p", label: "P-type implant", operation: "Implant" },
  { id: "contact", label: "Contact holes", operation: "Etch" },
  { id: "metal", label: "First metal", operation: "Etch" },
  { id: "via", label: "Via", operation: "Etch" },
  { id: "upper", label: "Upper metal", operation: "Etch" },
];

const cycle = (
  id: MaskId,
  prefix: string,
  key: string,
  title: string,
  operation: string,
  group: number,
): FabricationStep[] => {
  const definition = maskDefinitions.find((mask) => mask.id === id)!;
  const names = {
    coat: "Coat",
    expose: "Expose",
    develop: "Develop",
    strip: "Strip",
  };
  const step = (
    phase: Exclude<MaskPhase, "operate">,
    machine: MachineId,
  ): FabricationStep => ({
    key: `${prefix}${phase}`,
    title: `${names[phase]} · ${definition.label.toLowerCase()}`,
    operation:
      phase === "coat"
        ? "Apply a fresh photoresist coating"
        : phase === "expose"
          ? "Light changes the resist through this photomask"
          : phase === "develop"
            ? "Open the exposed positive resist"
            : "Remove the resist after it has protected the wafer",
    machine,
    group,
    mask: id,
    phase,
  });

  return [
    step("coat", "coat"),
    step("expose", "litho"),
    step("develop", "develop"),
    {
      key,
      title,
      operation,
      group,
      mask: id,
      phase: "operate",
      machine: definition.operation === "Implant" ? "implant" : "etch",
    },
    step("strip", "strip"),
  ];
};

export const steps: FabricationStep[] = [
  {
    key: "destination",
    title: "Our destination",
    operation: "A manufactured NOT gate",
    group: 0,
  },
  {
    key: "wafer",
    title: "One wafer, many circuits",
    operation: "Begin with a continuous silicon wafer",
    group: 1,
  },
  {
    key: "clean-room",
    title: "A place to work",
    operation: "Set the wafer beside our clean-room map",
    group: 1,
  },
  {
    key: "operator",
    title: "Meet our operator",
    operation: "Protective clothing helps keep particles off the wafer",
    group: 1,
  },
  {
    key: "hand-off",
    title: "One wafer in two views",
    operation: "The operator carries the same wafer we see below",
    group: 1,
  },
  {
    key: "magnify",
    title: "Look closer",
    operation: "Enlarge a small region of the silicon surface",
    group: 1,
  },
  {
    key: "layout",
    title: "The pattern comes first",
    operation: "Each operation has its own pattern",
    group: 1,
  },
  {
    key: "grow-oxide",
    title: "Grow a thin screen oxide",
    operation: "Oxidation consumes silicon as the film grows",
    machine: "furnace",
    group: 2,
  },
  ...cycle(
    "well",
    "",
    "well",
    "Implant the n-well",
    "Ions enter through the resist opening and thin oxide",
    2,
  ),
  {
    key: "well-anneal",
    title: "Heat the implanted well",
    operation: "Repair damage and establish the doped body region",
    machine: "anneal",
    group: 2,
  },
  {
    key: "isolation",
    title: "Grow thicker field oxide",
    operation: "Thicken the oxide before opening the device sites",
    machine: "furnace",
    group: 3,
  },
  ...cycle(
    "isolation",
    "isolation-",
    "prepare-isolation",
    "Etch the device openings",
    "Remove oxide at the exposed device sites",
    3,
  ),
  {
    key: "oxide",
    title: "Grow the gate insulation",
    operation: "Grow a thin oxide at each clean device site",
    machine: "furnace",
    group: 4,
  },
  {
    key: "poly",
    title: "Deposit the gate film",
    operation: "Add a conducting polysilicon film",
    machine: "deposit",
    group: 4,
  },
  ...cycle(
    "gate",
    "gate-",
    "pattern-gate",
    "Etch the gates",
    "Resist protects the gate strips while other polysilicon is removed",
    4,
  ),
  ...cycle(
    "n",
    "n-",
    "implant",
    "Implant n-type source and drain",
    "Resist, oxide and gates select where ions enter the silicon",
    5,
  ),
  ...cycle(
    "p",
    "p-",
    "implant-p",
    "Implant p-type source and drain",
    "A different resist pattern protects the previous device",
    5,
  ),
  {
    key: "anneal",
    title: "Activate the dopants",
    operation: "Controlled heating repairs damage and activates dopants",
    machine: "anneal",
    group: 5,
  },
  {
    key: "contact-insulation",
    title: "Insulate the devices",
    operation: "Deposit insulation before opening contact holes",
    machine: "deposit",
    group: 6,
  },
  ...cycle(
    "contact",
    "contact-",
    "contacts",
    "Etch the contact holes",
    "Open holes to the gate, source and drain terminals",
    6,
  ),
  {
    key: "metal",
    title: "Deposit the first metal",
    operation: "Fill the contacts and form a blanket metal film",
    machine: "metal",
    group: 6,
  },
  ...cycle(
    "metal",
    "metal-",
    "metal-pattern",
    "Etch the first wires",
    "Resist protects the intended wires while unwanted metal is removed",
    6,
  ),
  {
    key: "inverter",
    title: "A working NOT gate",
    operation: "Change the input to try it",
    group: 6,
  },
  {
    key: "interconnect",
    title: "Insulate the first wiring level",
    operation: "Deposit insulation over the existing wires",
    machine: "deposit",
    group: 7,
  },
  {
    key: "planarise",
    title: "Flatten the insulating film",
    operation: "Remove raised material to flatten the surface",
    machine: "polish",
    group: 7,
  },
  ...cycle(
    "via",
    "via-",
    "via",
    "Etch a via opening",
    "Stop at the intended wire on the level below",
    7,
  ),
  {
    key: "upper-metal",
    title: "Deposit the next metal",
    operation: "Fill the via and cover the insulating surface",
    machine: "metal",
    group: 7,
  },
  ...cycle(
    "upper",
    "upper-",
    "upper-metal-pattern",
    "Etch the upper wire",
    "Remove unwanted metal while resist protects the connection",
    7,
  ),
  {
    key: "finish",
    title: "From the wafer to a chip",
    operation: "Test, separate and package",
    machine: "inspect",
    group: 8,
  },
];

const stage = (key: string) => steps.findIndex((step) => step.key === key);
export const stages = {
  wafer: stage("wafer"),
  cleanRoom: stage("clean-room"),
  operator: stage("operator"),
  handOff: stage("hand-off"),
  magnify: stage("magnify"),
  layout: stage("layout"),
  growOxide: stage("grow-oxide"),
  develop: stage("develop"),
  well: stage("well"),
  wellAnneal: stage("well-anneal"),
  isolation: stage("isolation"),
  prepareIsolation: stage("prepare-isolation"),
  gateOxide: stage("oxide"),
  poly: stage("poly"),
  patternGate: stage("pattern-gate"),
  implant: stage("implant"),
  implantP: stage("implant-p"),
  anneal: stage("anneal"),
  contactInsulation: stage("contact-insulation"),
  contacts: stage("contacts"),
  metal: stage("metal"),
  metalPattern: stage("metal-pattern"),
  inverter: stage("inverter"),
  interconnect: stage("interconnect"),
  polish: stage("planarise"),
  via: stage("via"),
  upperMetal: stage("upper-metal"),
  upperMetalPattern: stage("upper-metal-pattern"),
  finish: stage("finish"),
};

export const maskCycles = maskDefinitions.map((definition) => ({
  ...definition,
  ...(Object.fromEntries(
    (["coat", "expose", "develop", "operate", "strip"] as const).map(
      (phase) => [
        phase,
        steps.findIndex(
          (step) => step.mask === definition.id && step.phase === phase,
        ),
      ],
    ),
  ) as Record<MaskPhase, number>),
}));
