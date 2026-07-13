.PHONY: doctor validate-skills devex-check context claim-status status browser-sync browser-install sol-check fable-check

doctor:
	python3 tools/devex/doctor.py

validate-skills:
	python3 tools/devex/validate_skills.py

devex-check:
	python3 tools/devex/check.py

context:
	python3 tools/devex/context.py

claim-status:
	python3 tools/devex/claim.py status

status:
	git status --short --branch

browser-sync:
	uv sync --project tools/browser

browser-install:
	uv run --project tools/browser playwright install chromium

sol-check:
	cargo fmt --manifest-path research/sol/Cargo.toml --all -- --check
	cargo test --manifest-path research/sol/Cargo.toml --workspace

fable-check:
	cargo test --manifest-path research/fable/Cargo.toml --workspace
