# Getting AWS access

You sign in to AWS with your Gradiated Google account. Every active Gradiated
Google Workspace account gets the `restricted` level automatically: it reads
and updates the shared development secrets under `gradiated/dev/`, which is
what `mise run env:build` uses to write your `.env`. It cannot see or change
anything else in AWS. Most people need nothing more.

## 1. Sign in and build your `.env`

1. Open the [AWS access portal](https://d-c3676db5af.awsapps.com/start) and
   sign in with Google using your Gradiated account. If the portal shows no
   AWS account yet, an administrator has not applied access since your Google
   account was created; ask in your onboarding issue.
2. In your checkout, run:

   ```sh
   mise run env:build
   ```

   The first run adds the `gradiated-restricted` AWS profile to
   `~/.aws/config` and opens a browser to sign in. It then writes `.env` from
   `gradiated/dev/env`. Rerun it whenever the shared secrets change.

## 2. Ask for more only if your role needs it

To get more than `restricted`, open a pull request that adds your Gradiated
primary email to
[`infra/bootstrap/identity-center/people.tf`](../infra/bootstrap/identity-center/people.tf)
with the extra levels, and say why. The Security Officer approves access under
the [System Access Control Policy](security/policies/system-access-control-policy.md).

```hcl
    "alex@gradiated.com" = ["readonly"]
```

| Level | What it allows |
| --- | --- |
| `restricted` | Read and update `gradiated/dev/` secrets. Everyone has it. |
| `readonly` | Read most of AWS, including production secret values. |
| `developer` | Change production outside identity, billing and security controls. |
| `admin` | Break-glass administration. |

CI cannot change AWS access. After the pull request merges, an administrator
applies it. Then sign in again with `mise run aws:login --profile <profile>`,
for example `gradiated-readonly`; see the
[infrastructure README](../infra/README.md) for the profiles.

## Applying access changes

For administrators. Apply the
[identity-center root](../infra/bootstrap/identity-center/README.md#review-and-adopt)
after an access pull request merges, and also when someone joins or leaves:
Google provisions and suspends users, and the apply adds or removes their
Restricted membership. The plan should change only those people.

To offboard someone, suspend or delete them in Google Workspace, remove their
`people.tf` entry if they have one, and apply. Google suspends their
Identity Center user; nobody deletes Identity Center users by hand.
