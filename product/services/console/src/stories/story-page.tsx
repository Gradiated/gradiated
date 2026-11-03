import NiceModal from "@ebay/nice-modal-react";
import { QueryClientProvider, useIsFetching } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { createStoryQueryClient } from "@/stories/query-client";
import { createConsoleRouter } from "@/router";

const Ready = () => {
  const fetching = useIsFetching();

  return <span hidden data-story-ready={fetching === 0} />;
};

export const StoryPage = ({ path }: { path: string }) => {
  const [queryClient] = useState(() => createStoryQueryClient());
  const [router] = useState(() =>
    createConsoleRouter(createMemoryHistory({ initialEntries: [path] })),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <NiceModal.Provider>
        <RouterProvider router={router} />
        <Toaster />
        <Ready />
      </NiceModal.Provider>
    </QueryClientProvider>
  );
};
