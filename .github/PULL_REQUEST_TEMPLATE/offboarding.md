## Offboarding

Track each system's access removal on a linked offboarding issue, as required by the System Access Control Policy. Link restricted evidence rather than copying personal data or credentials into this PR. Mark inapplicable items with a reason. Do not merge until access removal, asset return and sign-off are verified; track unresolved items with an owner and due date.

- Offboarding issue:
- Manager / checklist owner:
- Effective termination date and time (include timezone):
- Access revocation deadline (within one business day of effective termination):

## Continuing responsibilities and handover

- [ ] System administrators notified of separation and revocation deadline.
- [ ] Continuing confidentiality, intellectual property, data protection and other surviving contractual duties reiterated; acknowledgement or delivery evidence recorded.
- [ ] Ownership of company documents, repositories, services, billing, on-call duties and automation transferred to active owners.
- [ ] Company records preserved under retention and legal hold requirements before account deletion or device erasure.

## Verify removal of all access

Use the account/access inventory and administrator consoles to identify every system, including access outside SSO. Record each system, administrator, removal timestamp and verification evidence on the issue; do not rely solely on disabling Google sign-in.

- [ ] Google Workspace account disabled; active sessions and OAuth grants revoked.
- [ ] 1Password account and vault access removed; any shared credentials the departing person could retain rotated.
- [ ] GitHub organization, repositories, teams, deploy keys and personal token access revoked.
- [ ] AWS IAM Identity Center, direct IAM access, cloud roles and active sessions revoked.
- [ ] Tailscale, SSH keys, VPN/network and physical access revoked.
- [ ] Slack, Stripe, PostHog, RunPod/other GPU providers, incident.io, ClickHouse, Vercel, Drata and every other assigned SaaS/vendor account checked and access removed.
- [ ] API keys, tokens, certificates and other credentials issued to the person revoked or rotated; automation moved to approved service identities.
- [ ] Administrator verified every inventoried system's access removal within the deadline, with timestamps and evidence.

## Assets and company data

- [ ] Asset inventory reconciled; all company laptops, equipment, storage media, keys, badges and MFA tokens returned, with receipt evidence.
- [ ] Company files and data returned or transferred; removal from personal devices/accounts verified according to retention requirements.
- [ ] Returned assets recorded with their custodian and secure reuse/disposal handled under the Asset Management Policy.

## Verification

- Evidence references and completion dates:
- Manager sign-off / date:
- System administrator sign-off / date:
