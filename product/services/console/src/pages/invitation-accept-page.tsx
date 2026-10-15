import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate, useSearch } from "@tanstack/react-router";
import {
  ArrowRight,
  Check,
  CircleAlert,
  LoaderCircle,
  Mail,
  TriangleAlert,
  UserRound,
  X,
} from "lucide-react";
import type { ReactNode } from "react";

import {
  acceptInvitation,
  getCurrentUser,
  previewInvitation,
  type CurrentUser,
  type InvitationPreview,
} from "@/api/queries";
import { authClient } from "@/auth";
import { AuthCard } from "@/components/auth-card";
import { Button } from "@/components/ui/button";
import { useSession } from "@/hooks/use-session";
import { httpStatus } from "@/lib/errors";
import { INVITATION_TOKEN } from "@/lib/login-search";
import { queryKeys } from "@/lib/query-keys";
import { roleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { useWorkspaceSelection } from "@/store/workspace-selection";

type Details = Exclude<InvitationPreview, { status: "invalid" }>;

export const InvitationAcceptPage = () => {
  const { token } = useSearch({ from: "/invitations/accept" });
  const validToken = token !== undefined && INVITATION_TOKEN.test(token);
  const session = authClient.useSession();
  const preview = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => previewInvitation(token ?? ""),
    enabled: validToken,
    retry: false,
  });
  const me = useQuery({
    queryKey: queryKeys.me,
    queryFn: getCurrentUser,
    enabled: Boolean(session.data),
  });

  if (!validToken) return <InvalidInvitation />;
  const failed = [preview, me].find((query) => query.isError);
  if (failed) return <UnexpectedError onRetry={() => void failed.refetch()} />;
  if (!preview.data || session.isPending || (session.data && !me.data))
    return <Loading />;

  const invitation = preview.data;
  if (invitation.status === "invalid") return <InvalidInvitation />;
  if (invitation.status === "expired")
    return (
      <ExpiredInvitation organizationName={invitation.organization_name} />
    );

  const member = me.data?.organizations.find(
    (organization) => organization.id === invitation.organization_id,
  );
  if (member) return <AlreadyMember organization={member} />;
  if (invitation.status === "accepted") return <InvalidInvitation />;
  if (!session.data || !me.data)
    return <Navigate to="/login" search={{ invitation: token }} />;
  if (me.data.email.toLowerCase() !== invitation.email)
    return (
      <WrongAccount
        token={token}
        invitation={invitation}
        signedInAs={me.data.email}
      />
    );

  return (
    <JoinInvitation token={token} invitation={invitation} user={me.data} />
  );
};

const JoinInvitation = ({
  token,
  invitation,
  user,
}: {
  token: string;
  invitation: Details;
  user: CurrentUser;
}) => {
  const client = useQueryClient();
  const open = useOpenOrganization();
  const switchAccount = useSwitchAccount(token);
  const join = useMutation({
    mutationFn: () => acceptInvitation(token),
    onSuccess: open,
    onError: (error) => {
      if (httpStatus(error) === 409)
        void client.invalidateQueries({ queryKey: queryKeys.me });
    },
  });
  const status = join.error ? httpStatus(join.error) : undefined;

  if (status === 403)
    return (
      <WrongAccount
        token={token}
        invitation={invitation}
        signedInAs={user.email}
      />
    );
  if (status === 404) return <InvalidInvitation />;
  if (join.error && status !== 409)
    return <UnexpectedError onRetry={() => join.mutate()} />;

  return (
    <InvitationCard
      icon={<Mail />}
      title={`Join ${invitation.organization_name}`}
      footer={
        <p className="text-center text-sm text-muted-foreground">
          Signed in as {user.email} ·{" "}
          <button
            type="button"
            className="text-foreground underline underline-offset-4"
            onClick={() => void switchAccount()}
          >
            Not you?
          </button>
        </p>
      }
      action={
        <Button
          className="w-full"
          disabled={join.isPending}
          onClick={() => join.mutate()}
        >
          {join.isPending ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : null}
          Join {invitation.organization_name}
          {join.isPending ? null : <ArrowRight className="size-4" />}
        </Button>
      }
    >
      <p>
        You've been invited to join {invitation.organization_name} on Gradiated.
      </p>
      <dl className="mt-5 space-y-1.5 rounded-lg border bg-muted/30 px-4 py-3 text-sm">
        {[
          ["Organization", invitation.organization_name],
          ["Role", roleLabel(invitation.role)],
          ["Invited by", invitation.invited_by_email],
        ].map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="truncate font-medium text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
    </InvitationCard>
  );
};

const WrongAccount = ({
  token,
  invitation,
  signedInAs,
}: {
  token: string;
  invitation: Details;
  signedInAs: string;
}) => {
  const switchAccount = useSwitchAccount(token);

  return (
    <InvitationCard
      icon={<UserRound />}
      title={`This invitation is for ${invitation.email}`}
      action={
        <Button className="w-full" onClick={() => void switchAccount()}>
          Switch account
        </Button>
      }
    >
      You're signed in as {signedInAs}. Sign in with {invitation.email} to join{" "}
      {invitation.organization_name}.
    </InvitationCard>
  );
};

const ExpiredInvitation = ({
  organizationName,
}: {
  organizationName: string;
}) => (
  <InvitationCard
    icon={<TriangleAlert />}
    tone="warning"
    title="This invitation has expired"
    action={<ConsoleButton />}
  >
    Invitations last 7 days. Ask an admin of {organizationName} to send you a
    new one.
  </InvitationCard>
);

const InvalidInvitation = () => (
  <InvitationCard
    icon={<X />}
    tone="danger"
    title="This invitation link isn't valid"
    action={<ConsoleButton />}
  >
    It may have been revoked or already used. Ask the person who invited you to
    send a new one.
  </InvitationCard>
);

const AlreadyMember = ({
  organization,
}: {
  organization: CurrentUser["organizations"][number];
}) => {
  const open = useOpenOrganization();

  return (
    <InvitationCard
      icon={<Check />}
      tone="success"
      title={`You're already in ${organization.name}`}
      action={
        <Button className="w-full" onClick={() => void open(organization)}>
          Open {organization.name}
          <ArrowRight className="size-4" />
        </Button>
      }
    >
      You're already a member of this organization.
    </InvitationCard>
  );
};

const UnexpectedError = ({ onRetry }: { onRetry: () => void }) => (
  <InvitationCard
    icon={<CircleAlert />}
    tone="danger"
    title="We couldn't accept the invitation"
    action={
      <Button className="w-full" onClick={onRetry}>
        Try again
      </Button>
    }
  >
    Something went wrong on our side. Try again in a moment.
  </InvitationCard>
);

const Loading = () => (
  <AuthCard>
    <div className="grid min-h-48 place-items-center">
      <LoaderCircle
        aria-label="Loading invitation"
        className="size-5 animate-spin text-muted-foreground"
      />
    </div>
  </AuthCard>
);

const ConsoleButton = () => {
  const navigate = useNavigate();

  return (
    <Button className="w-full" onClick={() => void navigate({ to: "/" })}>
      Go to console
    </Button>
  );
};

const TONES = {
  neutral: "bg-muted text-foreground",
  success: "bg-[#e9f6b9] text-[#3f4c12]",
  warning: "bg-[#fff3c4] text-[#5a4a10]",
  danger: "bg-destructive/10 text-destructive",
} as const;

const InvitationCard = ({
  icon,
  tone = "neutral",
  title,
  children,
  action,
  footer,
}: {
  icon: ReactNode;
  tone?: keyof typeof TONES;
  title: string;
  children: ReactNode;
  action: ReactNode;
  footer?: ReactNode;
}) => (
  <AuthCard>
    <div className="p-6 md:p-9">
      <div
        className={cn(
          "mb-5 grid size-11 place-items-center rounded-lg [&>svg]:size-5",
          TONES[tone],
        )}
      >
        {icon}
      </div>
      <h1 className="text-2xl font-bold tracking-tight break-words">{title}</h1>
      <div className="mt-2 text-sm leading-6 text-muted-foreground">
        {children}
      </div>
      <div className="mt-7">{action}</div>
      {footer ? <div className="mt-5">{footer}</div> : null}
    </div>
  </AuthCard>
);

const useOpenOrganization = () => {
  const client = useQueryClient();
  const navigate = useNavigate();
  const selectOrganization = useWorkspaceSelection((s) => s.selectOrganization);
  const selectWorkspace = useWorkspaceSelection((s) => s.selectWorkspace);

  return async (organization: CurrentUser["organizations"][number]) => {
    selectOrganization(organization.id);
    selectWorkspace(organization.default_workspace_id);
    await client.invalidateQueries({ queryKey: queryKeys.me });
    await navigate({ to: "/models" });
  };
};

const useSwitchAccount = (token: string) => {
  const { signOut } = useSession();

  return () => signOut({ invitation: token });
};
