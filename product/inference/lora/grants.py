import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import uuid
from pathlib import Path

from artifacts import remaining, strict_json


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
        not (
            parsed.scheme == "https"
            or (
                parsed.scheme == "http"
                and parsed.hostname in ("localhost", "127.0.0.1", "::1")
            )
        )
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Invalid private artifact endpoint")


def read_private(url, identity, body=None, limit=65536, deadline=None):
    validate_endpoint(url)
    if deadline is None:
        deadline = time.monotonic() + 10
    parsed = urllib.parse.urlsplit(url)
    transport = (
        http.client.HTTPSConnection
        if parsed.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = transport(
        parsed.hostname, parsed.port, timeout=min(10, remaining(deadline))
    )
    try:
        connection.connect()
        socket = connection.sock
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        socket.settimeout(min(10, remaining(deadline)))
        connection.request(
            "POST" if body is not None else "GET",
            path,
            body=json.dumps(body).encode() if body is not None else None,
            headers={
                "Content-Type": "application/json",
                "X-Gradiated-Instance-Id": identity["instance_id"],
                "X-Gradiated-Nomad-Node-Id": identity["nomad_node_id"],
                "Authorization": f"Bearer {identity['token']}",
            },
        )
        socket.settimeout(min(10, remaining(deadline)))
        response = connection.getresponse()
        if response.status != 200:
            raise urllib.error.HTTPError(
                f"{parsed.scheme}://{parsed.hostname}",
                response.status,
                "Private API request failed",
                {},
                None,
            )
        data = bytearray()
        with response:
            while not response.isclosed():
                socket.settimeout(min(10, remaining(deadline)))
                chunk = response.read1(min(65536, limit + 1 - len(data)))
                remaining(deadline)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("Oversized artifact response")
        result = strict_json(data)
        remaining(deadline)
        return result
    finally:
        connection.close()


def api_url(base_url, path):
    validate_endpoint(base_url)
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.query or parsed.fragment:
        raise ValueError("API base URL cannot contain a query or fragment")
    return base_url.rstrip("/") + "/api/internal/v1/" + path


def production_targets(base_url, identity, base_model_id):
    url = api_url(base_url, "task-versions/production")
    result = read_private(
        url + "?" + urllib.parse.urlencode({"base_model_id": base_model_id}),
        identity,
        limit=1024 * 1024,
    )["data"]
    if not isinstance(result, list):
        raise TypeError("Invalid production list")
    return result


def resolver(base_url, identity):
    url = api_url(base_url, "adapter-downloads")

    def resolve(name, workspace_id, deadline=None):
        if not isinstance(name, str) or not 0 < len(name) <= 300:
            raise ValueError("Invalid version name")
        target = {"workspace_id": workspace_id, "version_name": name}
        grant = read_private(url, identity, target, deadline=deadline)
        version = grant["version"]
        if grant["workspace_id"] != workspace_id or version["name"] != name:
            raise ValueError("Artifact grant identity mismatch")
        return grant

    return resolve
