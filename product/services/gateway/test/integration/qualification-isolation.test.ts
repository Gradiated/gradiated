import { it } from "vitest";

import { useCases } from "./case.js";
import { checkQualificationIsolation } from "./qualification-isolation.js";

const { makeCase } = useCases();

it("isolates qualified deployments from ordinary traffic and rejects unauthorized or draining targets", async () => {
  const instance = await makeCase("vllm", { replicas: 2 });
  const outsider = await makeCase("vllm");
  await checkQualificationIsolation(
    instance,
    outsider,
    instance.body(),
    async (response) => {
      await instance.settled(response, { charge: 1060 });
    },
  );
});
