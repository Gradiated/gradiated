# Gradiated

Gradiated serves exact hosted models to customers through its gateway and proxy, and runs the control plane that owns organizations, API keys, the model catalog, billing and usage.

## trust levels
- anonymous (outside): Any HTTP request from the internet with no session: sign-in and sign-up, the waitlist, health and the public model list.
- customer-session (outside): A browser request with a Better Auth session cookie. The user is known; the organizations and workspaces it may reach are not, until membership is checked.
- customer-api-key (outside): A request that presents a workspace API key as a bearer token or x-api-key header. The key names one workspace and the member who created it; that member's access is still checked.
- stripe (outside): A webhook request that claims to come from Stripe. It is trusted only after its signature verifies against the webhook secret.
- service-token (outside): A request from a Gradiated host process, such as a readiness or profiling report, that presents a bearer token. The token names the reporter; the body is still unvalidated input.
- operator (outside): An agent or staff member that calls the ops MCP over the internet. It is trusted only after a verified Gradiated Google login and a scoped MCP token.
- local-user (outside): The person who runs the wizard on their own machine, with their own files and credentials.
- control-plane: Rows the TypeScript control plane writes to PostgreSQL: organizations, memberships, workspaces, API-key digests, the catalog and balance transactions.
- serving-state: What the gateway writes to Valkey for the control plane to read back: finalized generation events and runtime status.
- cluster: What the Kubernetes API reports about model allocations and their hosts.
- production-read: What the ops MCP tools read and return from Prometheus, Loki, Alertmanager, Kubernetes and Kubernetes.
