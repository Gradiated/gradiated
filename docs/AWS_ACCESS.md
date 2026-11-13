# Getting AWS access

Everyone at Gradiated gets AWS access through a pull request. Most people need
only the `restricted` level: it reads and updates the shared development
secrets under `gradiated/dev/`, which is what `mise run env:build` uses to write
your `.env`. It cannot see or change anything else in AWS.

## 1. Add yourself

Open a pull request that adds you to
[`infra/bootstrap/identity-center/people.tf`](../infra/bootstrap/identity-center/people.tf):

```hcl
    alex = {
      given_name  = "Alex"
      family_name = "Morgan"
      email       = "alex@gradiated.com"
      access      = ["restricted"]
    }
```

- The key (`alex`) is your sign-in username: your lowercase first name, as in
  your Gradiated email.
- Use your Gradiated email. Leave out `user_id`; AWS assigns it.
- Ask only for the levels your role needs. If you need more than `restricted`,
  say why in the pull request; the Security Officer approves access under the
  [System Access Control Policy](security/policies/system-access-control-policy.md).

| Level | What it allows |
| --- | --- |
| `restricted` | Read and update `gradiated/dev/` secrets. The default. |
| `readonly` | Read most of AWS, including production secret values. |
| `developer` | Change production outside identity, billing and security controls. |
| `admin` | Break-glass administration. |

Link the pull request from your onboarding issue.

## 2. Wait for the apply

CI cannot change AWS access. After the pull request merges, an administrator
applies it (see [Applying access changes](#applying-access-changes)). Nobody
sends you an email; you set your password on your first sign-in.

## 3. Sign in and build your `.env`

1. Open <https://d-c3676db5af.awsapps.com/start> and enter your username
   (your key in `people.tf`, such as `james`). AWS emails you a one-time
   code; enter it, set a password, and register an MFA device when asked. Use
   an authenticator app or a security key.
2. In your checkout, run:

   ```sh
   mise run env:build
   ```

   The first run adds the `gradiated-restricted` AWS profile to
   `~/.aws/config` and opens a browser to sign in. It then writes `.env` from
   `gradiated/dev/env`. Rerun it whenever the shared secrets change.

If it says you cannot read the secret, check that your pull request was applied.

## Applying access changes

For administrators. Review the plan before applying; it should only add or
change the people in the pull request.

```sh
mise run aws:login --profile gradiated-admin
export AWS_PROFILE=gradiated-admin
```

Then initialise and apply as described in the
[identity-center README](../infra/bootstrap/identity-center/README.md#review-and-adopt).
New people need no password email: Identity Center has **Send email OTP for
users without a password** on (Settings → Authentication → Standard
authentication), so their first sign-in emails them a one-time code.

To remove access, remove the level from the person's `access` list. To offboard
someone, also disable their user in Identity Center; deletion protection keeps
the user record for the access review.
