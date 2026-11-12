import { useProductContext } from "@/hooks/use-product-context";
import { privateModelName } from "@/lib/model-name";

// A bare task name would not resolve, so hold the slug's place until it loads.
export const usePrivateModelName = () => {
  const { selectedOrganization } = useProductContext();

  return (task: string, version?: string) =>
    privateModelName(selectedOrganization?.slug ?? "…", task, version);
};
