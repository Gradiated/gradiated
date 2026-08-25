# Metabase production deployment

- Date: 2026-08-25
- Status: accepted and implemented
- Evidence type: vendor-reported, measured, and inferred

## Question

How should Gradiated run Metabase for internal analytics in the production EKS
cluster?

## Decision

Run one Metabase Open Source pod at `metabase.gradiated.com`. Use the existing
Gateway API ALB, wildcard ACM certificate, ExternalDNS, External Secrets,
Prometheus, and Grafana platform.

Use one dedicated Single-AZ RDS PostgreSQL 17 instance for Metabase state. Use
class `db.t4g.small` and 20 GiB gp3 storage. Keep backups, encryption, deletion
protection, and a final snapshot. Do not add a persistent volume, Redis, SMTP,
a second ALB, or a WAF.

Use Google Sign-In. Permit automatic account creation only for
`gradiated.com`. Disable public sharing, anonymous tracking, update checks, AI
features, sample content, and surveys.

Create one `metabase_reader` role in each analytics database. PostgreSQL grants
`SELECT` on all current `public` tables and on future tables that
`gradiated_app` creates. ClickHouse grants `SELECT` on `gradiated.*`. This broad
read scope is accepted for the initial internal deployment. Metabase gets no
product write permission.

Store generated database credentials in AWS Secrets Manager. RDS manages the
Metabase application database secret. Terraform uses ephemeral passwords and
write-only provider arguments for both analytics readers. The Metabase
encryption key and Google client ID use the externally populated
`platform/metabase` secret.

## Evidence

Vendor-reported evidence:

- Metabase recommends PostgreSQL as the production application database:
  https://www.metabase.com/docs/latest/installation-and-operation/configuring-application-database
- Metabase documents the Google client ID and allowed auto-create domain:
  https://www.metabase.com/docs/latest/people-and-groups/google-sign-in
- Metabase documents the health endpoint and Prometheus port:
  https://www.metabase.com/docs/latest/installation-and-operation/monitoring-metabase
- Metabase includes ClickHouse as an official driver. The ClickHouse driver has
  been bundled since Metabase 54:
  https://www.metabase.com/docs/latest/databases/connections/clickhouse
  and https://github.com/ClickHouse/metabase-clickhouse-driver
- Metabase documents that the encryption key must be a base64 value with at
  least 16 characters:
  https://www.metabase.com/docs/latest/configuring-metabase/environment-variables

Measured evidence on 2026-08-25:

- The EKS CPU nodes have enough requested CPU and memory for one pod that
  requests 500 millicores and 2 GiB.
- The issued ACM certificate covers `*.gradiated.com` and is attached to the
  shared ALB.
- The Gateway is accepted and programmed.
- The selected Metabase image is `v0.63.14` at digest
  `sha256:7fa304e677216ebafe81c4b55ce365b4fdc485673000846f7ca5a7cb7381a495`.
- The dedicated RDS instance is available. It is private, encrypted,
  Single-AZ, deletion-protected, and uses PostgreSQL 17.9.
- The Metabase platform secret and both analytics reader secrets have current
  versions in AWS Secrets Manager.
- All five changed Terraform units reported no changes after the scoped
  production applies.

Inferred evidence:

- One pod and Single-AZ state storage meet the accepted internal-use
  availability target.
- The current broad reader grants reduce setup work but increase the effect of
  a Metabase account or application compromise.

## Quality gate

The change must pass Terraform format and validation, Terragrunt validation,
the Kubernetes render, focused TypeScript checks, dashboard JSON parsing,
DevEx checks, and diff hygiene. Each production apply must affect only its
reviewed unit. A final plan for every changed unit must report no changes.

## Follow-up

Verify Argo, Google Sign-In, both read-only data connections, the public health
probe, alerts, and the Grafana dashboard. Create the first administrator and
store its recovery credentials in the team password manager.
