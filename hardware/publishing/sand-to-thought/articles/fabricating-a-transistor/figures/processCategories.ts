import type { FabricationStep } from "./sequence";

export const processCategories = [
  { id: "pattern", label: "Patterning", short: "Pattern" },
  { id: "add", label: "Adding material", short: "Add" },
  { id: "remove", label: "Removing material", short: "Remove" },
  { id: "modify", label: "Modifying material", short: "Modify" },
  { id: "clean", label: "Cleaning", short: "Clean" },
  { id: "inspect", label: "Inspecting / measuring", short: "Inspect" },
] as const;

export type ProcessCategory = (typeof processCategories)[number]["id"];

const machineCategories: Partial<
  Record<NonNullable<FabricationStep["machine"]>, ProcessCategory>
> = {
  coat: "pattern",
  litho: "pattern",
  develop: "pattern",
  furnace: "add",
  deposit: "add",
  metal: "add",
  etch: "remove",
  strip: "remove",
  polish: "remove",
  implant: "modify",
  anneal: "modify",
  inspect: "inspect",
};

export const processCategoryFor = (
  step: FabricationStep,
): ProcessCategory | undefined =>
  step.machine ? machineCategories[step.machine] : undefined;
