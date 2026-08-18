# Gateway

The Rust inference data plane belongs here. It authenticates and admits direct
and OpenRouter inference requests through Valkey and streams one exact model
from SGLang. It does not import TypeScript control-plane code; shared wire
contracts are generated as Rust fixtures from `packages/contracts`.

The proposed component model and complete request lifecycle are documented in
[ARCHITECTURE.md](ARCHITECTURE.md). Review that design before gateway code is
implemented.
