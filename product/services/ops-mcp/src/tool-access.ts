export interface ToolAccess {
  readonly ingress: "public" | "private";
}

export const requirePrivateToolAccess = (access: ToolAccess): void => {
  if (access.ingress !== "private") {
    throw new Error(
      "This tool requires the private administrative MCP connection. Connect through Tailscale and the private Kubernetes port-forward; OAuth is still required.",
    );
  }
};
