import json
import re
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from artifacts import NoRedirect, strict_json


def host_identity(path):
    identity = strict_json(Path(path).read_bytes())
    for key in ("instance_id", "nomad_node_id"):
        if str(uuid.UUID(identity[key])) != identity[key]:
            raise ValueError("Invalid host identity")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", identity["token"]):
        raise ValueError("Invalid host credential")
    return identity


def validate_endpoint(url):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Invalid private artifact endpoint")


def read_private(url, identity, body=None, limit=65536):
    validate_endpoint(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            "X-Gradiated-Instance-Id": identity["instance_id"],
            "X-Gradiated-Nomad-Node-Id": identity["nomad_node_id"],
            "Authorization": f"Bearer {identity['token']}",
        },
    )
    with urllib.request.build_opener(NoRedirect()).open(
        request, timeout=10
    ) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Oversized artifact response")
        return strict_json(data)


def production_targets(url, identity, base_model_id):
    separator = "&" if "?" in url else "?"
    result = read_private(
        url + separator + urllib.parse.urlencode({"base_model_id": base_model_id}),
        identity,
        limit=1024 * 1024,
    )["data"]
    if not isinstance(result, list):
        raise TypeError("Invalid production list")
    return result


def resolver(url, identity):
    validate_endpoint(url)

    def resolve(name, workspace_id):
        match = re.fullmatch(r"ft-([a-f0-9-]{36})-([a-f0-9]{64})", name)
        if not match:
            raise ValueError("Invalid adapter identity")
        target = {
            "workspace_id": workspace_id,
            "version_id": match[1],
            "sha256": match[2],
        }
        grant = read_private(url, identity, target)
        version = grant["version"]
        if (
            grant["workspace_id"] != workspace_id
            or version["id"] != match[1]
            or version["adapter"]["sha256"] != match[2]
        ):
            raise ValueError("Artifact grant identity mismatch")
        return grant

    return resolve
