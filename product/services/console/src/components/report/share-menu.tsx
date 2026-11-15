import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link2, LoaderCircle, Share2 } from "lucide-react";
import { toast } from "sonner";

import { getVersionShare } from "@/api/training";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { errorMessage } from "@/lib/errors";

type VersionPath = {
  workspace_id: string;
  task: string;
  version_id: string;
};

const sharedReportUrl = (link: { version_id: string; signature: string }) =>
  `${window.location.origin}/share/${link.version_id}/${link.signature}`;

// Safari allows clipboard writes only during the click, so pass the link as a promise.
const copyText = async (text: Promise<string>) => {
  if (
    typeof ClipboardItem !== "undefined" &&
    ClipboardItem.supports?.("text/plain")
  ) {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/plain": text.then(
          (value) => new Blob([value], { type: "text/plain" }),
        ),
      }),
    ]);
    return;
  }

  await navigator.clipboard.writeText(await text);
};

export const ShareMenu = ({
  path,
  queryKey,
}: {
  path: VersionPath;
  queryKey: readonly unknown[];
}) => {
  const client = useQueryClient();
  const copy = useMutation({
    mutationFn: async () => {
      const link = client
        .fetchQuery({
          queryKey,
          queryFn: () => getVersionShare(path),
          staleTime: Infinity,
        })
        .then(sharedReportUrl);
      link.catch(() => undefined);

      try {
        await copyText(link);
      } catch (error) {
        await link;
        throw error;
      }
    },
    onSuccess: () => toast.success("Public link copied"),
    onError: (error) =>
      toast.error(errorMessage(error, "The link could not be copied.")),
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline">
          {copy.isPending ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : (
            <Share2 className="size-4" />
          )}
          Share
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem
          disabled={copy.isPending}
          onSelect={() => copy.mutate()}
        >
          <Link2 className="size-4" />
          Copy public link
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
