from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def event_id(event: dict[str, Any]) -> str:
    source = "|".join(
        str(event.get(key, ""))
        for key in ("timestamp", "role", "label", "stdout_path")
    )
    return hashlib.sha256(source.encode()).hexdigest()


def research_update(lab_dir: Path, event: dict[str, Any]) -> str:
    label = str(event.get("label", "unknown"))
    status_path = lab_dir / "projects" / label / "STATUS.json"
    try:
        status = json.loads(status_path.read_text())
    except (OSError, json.JSONDecodeError):
        status = {}
    title = "GLM research result"
    campaign_path = lab_dir / "CAMPAIGN.md"
    if campaign_path.is_file():
        first = next(
            (line.removeprefix("# ").strip() for line in campaign_path.read_text().splitlines() if line.startswith("# ")),
            "",
        )
        if first:
            title = first
    outcome = str(status.get("summary") or "Researcher turn completed without a status summary.")
    next_action = str(status.get("next_action") or "No next action recorded.")
    project_status = str(status.get("status") or "unknown")
    experiment = status.get("last_experiment") or status.get("active_experiment")
    lines = [
        title,
        f"Project: {label}",
        f"Status: {project_status}",
    ]
    if experiment:
        lines.append(f"Experiment: {experiment}")
    lines.extend((f"Result: {outcome}", f"Next: {next_action}"))
    return "\n".join(lines)[:3500]


def whatsapp_payload(
    recipient: str,
    text: str,
    *,
    template_name: str | None,
    template_language: str,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
    }
    if template_name:
        return {
            **base,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": template_language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": text}],
                    }
                ],
            },
        }
    return {**base, "type": "text", "text": {"preview_url": False, "body": text}}


@dataclass(frozen=True)
class WhatsAppCloudSender:
    access_token: str
    phone_number_id: str
    recipient: str
    graph_version: str = "v23.0"
    template_name: str | None = None
    template_language: str = "en_US"
    opener: Callable[..., Any] = urllib.request.urlopen

    @classmethod
    def from_environment(cls) -> "WhatsAppCloudSender":
        required = {
            "access_token": os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip(),
            "phone_number_id": os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            "recipient": os.environ.get("WHATSAPP_RECIPIENT", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError("missing WhatsApp configuration: " + ", ".join(missing))
        return cls(
            **required,
            graph_version=os.environ.get("WHATSAPP_GRAPH_VERSION", "v23.0").strip(),
            template_name=os.environ.get("WHATSAPP_TEMPLATE_NAME", "").strip() or None,
            template_language=os.environ.get("WHATSAPP_TEMPLATE_LANGUAGE", "en_US").strip(),
        )

    def send(self, text: str) -> str:
        payload = whatsapp_payload(
            self.recipient,
            text,
            template_name=self.template_name,
            template_language=self.template_language,
        )
        request = urllib.request.Request(
            f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=20) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:1000]
            raise RuntimeError(f"WhatsApp HTTP {error.code}: {detail}") from error
        messages = result.get("messages", [])
        return str(messages[0].get("id", "accepted")) if messages else "accepted"


class ResultNotifier:
    def __init__(self, lab_dir: Path, state_path: Path, sender: Any):
        self.lab_dir = lab_dir
        self.events_path = lab_dir / "runtime" / "events.jsonl"
        self.delivery_events = lab_dir / "runtime" / "notification_events.jsonl"
        self.state_path = state_path
        self.sender = sender
        if state_path.is_file():
            self.state = json.loads(state_path.read_text())
        else:
            self.state = {
                "schema_version": 1,
                "offset": self.events_path.stat().st_size if self.events_path.is_file() else 0,
                "pending": [],
            }
            self._save()

    def _save(self) -> None:
        atomic_json(self.state_path, self.state)

    def read_new_events(self) -> None:
        if not self.events_path.is_file():
            return
        size = self.events_path.stat().st_size
        if size < self.state["offset"]:
            self.state["offset"] = 0
        with self.events_path.open() as handle:
            handle.seek(self.state["offset"])
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") == "agent_completed" and event.get("role") == "researcher":
                    self.state["pending"].append(
                        {"id": event_id(event), "event": event, "attempts": 0, "next_attempt": 0}
                    )
            self.state["offset"] = handle.tell()
        self._save()

    def deliver_pending(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        remaining = []
        for item in self.state["pending"]:
            if item["next_attempt"] > now:
                remaining.append(item)
                continue
            event = item["event"]
            try:
                message_id = self.sender.send(research_update(self.lab_dir, event))
            except Exception as error:
                item["attempts"] += 1
                item["next_attempt"] = now + min(900, 15 * (2 ** min(item["attempts"], 6)))
                remaining.append(item)
                append_jsonl(
                    self.delivery_events,
                    {
                        "event": "notification_failed",
                        "event_id": item["id"],
                        "project": event.get("label"),
                        "attempts": item["attempts"],
                        "error": f"{type(error).__name__}: {error}",
                    },
                )
            else:
                append_jsonl(
                    self.delivery_events,
                    {
                        "event": "notification_sent",
                        "event_id": item["id"],
                        "project": event.get("label"),
                        "message_id": message_id,
                    },
                )
        self.state["pending"] = remaining
        self._save()

    def run_forever(self, poll_seconds: float) -> None:
        while True:
            self.read_new_events()
            self.deliver_pending()
            time.sleep(poll_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send research results to WhatsApp")
    parser.add_argument("--lab-config", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=10)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    config = json.loads(args.lab_config.read_text())
    sender = WhatsAppCloudSender.from_environment()
    notifier = ResultNotifier(Path(config["lab_dir"]), args.state_file, sender)
    if args.once:
        notifier.read_new_events()
        notifier.deliver_pending()
        return 0
    notifier.run_forever(args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
