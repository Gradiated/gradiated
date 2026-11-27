import { Download, LoaderCircle, Rocket } from "lucide-react";
import { useState } from "react";

import { DeployDialog } from "@/components/training/deploy-dialog";
import { DetailList, SectionCard } from "@/components/training/training-ui";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDownloadArtifact } from "@/hooks/use-grad";
import { formatBytes, formatDateTime } from "@/lib/grad/format";
import { DEPLOYABLE_FORMATS, FORMAT_LABEL } from "@/lib/grad/labels";
import type { Artifact } from "@/lib/grad/types";

const deployBlocker = (artifact: Artifact, canDeploy: boolean) => {
  if (!artifact.format || !DEPLOYABLE_FORMATS.has(artifact.format))
    return "Deploy supports LoRA adapters and cartridges for now.";
  if (!canDeploy) return "Only workspace admins can deploy models.";

  return null;
};

export const ArtifactCard = ({
  artifact,
  loading,
  canDeploy,
}: {
  artifact: Artifact | undefined;
  loading: boolean;
  canDeploy: boolean;
}) => {
  const [deployOpen, setDeployOpen] = useState(false);
  const download = useDownloadArtifact();

  if (loading || !artifact) {
    return (
      <SectionCard title="Artifact">
        {loading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <p className="text-sm text-muted-foreground">
            The artifact is uploaded when the run completes.
          </p>
        )}
      </SectionCard>
    );
  }

  const blocker = deployBlocker(artifact, canDeploy);

  return (
    <SectionCard
      title="Artifact"
      description={`${artifact.name}@${artifact.version}`}
      actions={
        <>
          <Button
            variant="outline"
            size="sm"
            disabled={download.isPending}
            onClick={() =>
              download.mutate({
                id: artifact.id,
                fileName: `${artifact.name}-${artifact.version}.grad.tar.gz`,
              })
            }
          >
            {download.isPending ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <Download />
            )}
            Download
          </Button>
          <Button
            size="sm"
            disabled={blocker !== null}
            onClick={() => setDeployOpen(true)}
          >
            <Rocket />
            Deploy
          </Button>
        </>
      }
    >
      <DetailList
        items={[
          {
            label: "Format",
            value: artifact.format
              ? (FORMAT_LABEL[artifact.format] ?? artifact.format)
              : "—",
          },
          { label: "Base model", value: artifact.baseModel },
          { label: "Size", value: formatBytes(artifact.sizeBytes) },
          { label: "Created", value: formatDateTime(artifact.createdAt) },
          {
            label: "SHA-256",
            value: (
              <code className="font-mono text-xs" title={artifact.sha256}>
                {artifact.sha256.slice(0, 16)}…
              </code>
            ),
          },
          {
            label: "ID",
            value: <code className="font-mono text-xs">{artifact.id}</code>,
          },
        ]}
      />
      {blocker ? (
        <p className="mt-4 text-xs text-muted-foreground">{blocker}</p>
      ) : null}
      {deployOpen ? (
        <DeployDialog
          artifact={artifact}
          open={deployOpen}
          onOpenChange={setDeployOpen}
        />
      ) : null}
    </SectionCard>
  );
};
