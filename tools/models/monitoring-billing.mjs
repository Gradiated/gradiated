import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

export const configureMonitoringBilling = async (
  client,
  { workspaceId, applyCredit = false, postCredit },
) => {
  if (workspaceId !== "01a0ec7f-68fc-7149-b314-e600ed3d579a")
    throw new Error("Refusing to change an unrecognized monitoring workspace");

  const result = await client.query(
    `SELECT o.id, o.name, o.status, b.mode, b.balance::text
     FROM organizations o
     JOIN billing_accounts b ON b.organization_id = o.id
     JOIN workspaces w ON w.organization_id = o.id
     WHERE w.id = $1`,
    [workspaceId],
  );
  const account = result.rows[0];
  if (
    result.rows.length !== 1 ||
    account.id !== "01a039af-0aae-7459-b9bf-eb346420f6b3" ||
    account.name !== "Gradiated" ||
    account.status !== "active" ||
    account.mode !== "prepaid"
  )
    throw new Error(
      "Refusing to change an unrecognized monitoring account or billing policy",
    );

  if (!applyCredit) return account;

  const posted = await postCredit({
    organizationId: account.id,
    type: "credit",
    amount: 10_000_000_000_000n,
    sourceType: "operator",
    sourceId: "gradiated-inference-monitoring-reserve-v1",
    createdBy: null,
  });
  return {
    ...account,
    transactionId: posted.id,
    sourceId: posted.sourceId,
    creditNanoUsd: posted.amount.toString(),
    postedBalanceNanoUsd: posted.balanceAfter.toString(),
  };
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const [flag] = process.argv.slice(2);
  if (process.argv.length > 3 || (flag && flag !== "--apply-credit"))
    throw new Error("Usage: monitoring-billing.mjs [--apply-credit]");

  const script = `
    import { createControlDatabase, createBillingService } from './packages/control/dist/index.js';
    const { database, pool } = createControlDatabase(process.env.DATABASE_URL, 1);
    try {
      const configure = ${configureMonitoringBilling.toString()};
      console.log(JSON.stringify(await configure(pool, {
        workspaceId: process.env.MODEL_VERIFICATION_WORKSPACE_ID,
        applyCredit: ${flag === "--apply-credit"},
        postCredit: entry => createBillingService(database).applyBalanceTransaction(entry),
      })));
    } finally { await pool.end(); }
  `;
  execFileSync(
    "kubectl",
    [
      "--context",
      "arn:aws:eks:us-east-1:873716897517:cluster/gradiated-prod",
      "--request-timeout=30s",
      "-n",
      "gradiated",
      "exec",
      "-i",
      "deployment/worker",
      "-c",
      "worker",
      "--",
      "node",
      "--input-type=module",
      "-",
    ],
    { input: script, stdio: ["pipe", "inherit", "inherit"], timeout: 45_000 },
  );
}
