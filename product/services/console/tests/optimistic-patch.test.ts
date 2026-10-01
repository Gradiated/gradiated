import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import {
  useOptimisticPatch,
  useOptimisticValue,
} from "../src/hooks/use-optimistic-patch";

it("serializes rapid edits, retains queued intent after a failure, and rolls back the final failure", async () => {
  const client = new QueryClient();
  const key = ["settings"];
  type Value = { enabled: boolean; days: number };
  type Patch = Partial<Value>;
  const requests: {
    resolve: (value: Value) => void;
    reject: (error: Error) => void;
  }[] = [];
  client.setQueryData(key, { enabled: false, days: 30 });
  let mutate!: (patch: Patch) => Promise<Value>;
  const Harness = () => {
    const save = useOptimisticPatch({
      mutationKey: key,
      queryKey: key,
      mutationFn: (_patch: Patch) =>
        new Promise<Value>((resolve, reject) => {
          requests.push({ resolve, reject });
        }),
      commit: (value) => {
        client.setQueryData(key, value);
      },
    });
    mutate = save.mutateAsync;
    const value = useOptimisticValue<Value, Patch>(
      key,
      client.getQueryData<Value>(key)!,
      (current, patch) => ({ ...current, ...patch }),
    );
    return createElement("span", null, JSON.stringify(value));
  };
  const read = () =>
    renderToStaticMarkup(
      createElement(QueryClientProvider, { client }, createElement(Harness)),
    ).replaceAll("&quot;", '"');
  read();
  const first = mutate({ enabled: true }).catch((error: Error) => error);
  const second = mutate({ days: 90 });
  expect(read()).toContain('"enabled":true,"days":90');
  await vi.waitFor(() => expect(requests).toHaveLength(1));
  requests[0]!.reject(new Error("Save failed"));
  expect(await first).toMatchObject({ message: "Save failed" });
  expect(read()).toContain('"enabled":false,"days":90');
  await vi.waitFor(() => expect(requests).toHaveLength(2));
  requests[1]!.resolve({ enabled: false, days: 90 });
  await second;
  expect(read()).toContain('"enabled":false,"days":90');
  const third = mutate({ enabled: true }).catch((error: Error) => error);
  const fourth = mutate({ enabled: false, days: 180 });
  expect(read()).toContain('"enabled":false,"days":180');
  await vi.waitFor(() => expect(requests).toHaveLength(3));
  requests[2]!.resolve({ enabled: true, days: 90 });
  await third;
  expect(read()).toContain('"enabled":false,"days":180');
  await vi.waitFor(() => expect(requests).toHaveLength(4));
  requests[3]!.resolve({ enabled: false, days: 180 });
  await fourth;
  const last = mutate({ enabled: true }).catch((error: Error) => error);
  expect(read()).toContain('"enabled":true');
  await vi.waitFor(() => expect(requests).toHaveLength(5));
  requests[4]!.reject(new Error("Save failed"));
  await last;
  expect(read()).toContain('"enabled":false,"days":180');
});

it("uses the same write queue for equivalent query keys", async () => {
  const client = new QueryClient();
  const requests: (() => void)[] = [];
  let reverseKey = false;
  let mutate!: () => Promise<void>;
  const Harness = () => {
    const mutationKey = [
      "settings",
      reverseKey
        ? { workspace: "workspace", organization: "organization" }
        : { organization: "organization", workspace: "workspace" },
    ];
    const save = useOptimisticPatch({
      mutationKey,
      queryKey: ["workspaces"],
      mutationFn: (_patch: void) =>
        new Promise<void>((resolve) => {
          requests.push(resolve);
        }),
      commit: () => {},
    });
    mutate = () => save.mutateAsync();

    return null;
  };
  const render = () =>
    renderToStaticMarkup(
      createElement(QueryClientProvider, { client }, createElement(Harness)),
    );
  render();
  const first = mutate();
  await vi.waitFor(() => expect(requests).toHaveLength(1));
  reverseKey = true;
  render();
  const second = mutate();
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
  expect(requests).toHaveLength(1);
  requests[0]!();
  await first;
  await vi.waitFor(() => expect(requests).toHaveLength(2));
  requests[1]!();
  await second;
});
