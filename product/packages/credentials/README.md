# Provider credentials

TypeScript and Rust services use this package to load one active provider key.
The loader maps the provider to its production Secrets Manager name in
`us-east-1`. It reads `AWSCURRENT` on each call. It keeps no key cache.

```ts
import { CredentialLoader } from "@gradiated/credentials";

const credentials = new CredentialLoader();
const apiKey = await credentials.load("openai");
```

The TypeScript provider type is `"openai" | "anthropic"`. Add
`"@gradiated/credentials": "workspace:*"` to a service's dependencies before use.
You can pass a configured `SecretsManagerClient` to the constructor.

```rust
use gradiated_credentials::{CredentialLoader, Provider};

let credentials = CredentialLoader::new(secrets_manager_client);
let api_key = credentials.load(Provider::OpenAi).await?;
```

Add a Cargo path dependency on this directory before use. Configure the Rust
AWS client for `us-east-1` with the service's AWS credential provider. A container
build must include this directory in its build context.

Each stored value contains `primaryApiKey`, `secondaryApiKey`, and `activeSlot`.
Only the loader handles these fields. It returns the selected key as a string.
An invalid slot, missing active key, or failed read returns a generic error.
The loader does not return the inactive key after an error.

To rotate a key, update the inactive key in Secrets Manager. Test that key.
Change `activeSlot` to select it. The next load reads the selected key. If a
service keeps a provider client, reload its key or restart the service before
revoking the old key. Do not call the loader on each inference request.

No service currently consumes these stored keys. Grant `GetSecretValue` on the
specific provider secret and `kms:Decrypt` on its KMS key when adding a consumer.
The customer-key proxy continues to use the key supplied with each request.

Run `pnpm --filter @gradiated/credentials check` from `product/` to check both
implementations. The tests use synthetic keys and a local AWS HTTP endpoint.
