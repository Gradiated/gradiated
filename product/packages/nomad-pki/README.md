# Nomad PKI

Issues and renews Nomad TLS certificates signed by the Nomad CA, whose key
exists only in the KMS key `alias/gradiated-prod-nomad-ca`. Certificates are
built with `@peculiar/asn1-x509` and signed through `kms:Sign`, which returns
the DER signature X.509 stores.

- `issueCertificate` and the `host`, `cli` and `server-N` profiles: used by
  GPU instance registration in the ops MCP.
- `renewingCertificate`: keeps a certificate in memory and reissues it once two
  thirds of its lifetime has passed; the ops MCP renews its own this way.
- `dist/renewer.js`: runs beside a Nomad server or the UI proxy, renews
  `cert.pem` and `key.pem` in a shared directory, sends `SIGHUP` to the process
  it serves and reports `nomad_certificate_expiry_timestamp_seconds`.
- `pnpm --filter @gradiated/nomad-pki certificate --role <role> --ca <ca.pem>
--out <dir>`: issues a certificate by hand for one that does not renew itself.

See "Certificate renewal" in the Nomad README for operations and alerts.
