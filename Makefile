.PHONY: doctor validate-skills devex-check start context status browser-sync browser-install lab-check

doctor:
	python3 tools/devex/doctor.py

validate-skills:
	python3 tools/devex/validate_skills.py

devex-check:
	python3 tools/devex/check.py

start:
	python3 tools/devex/start.py

context:
	python3 tools/devex/context.py

status:
	git status --short --branch

browser-sync:
	uv sync --project tools/browser

browser-install:
	uv run --project tools/browser playwright install chromium

lab-check:
	cargo fmt --manifest-path research/lab/Cargo.toml --all -- --check
	cargo test --manifest-path research/lab/Cargo.toml --workspace
