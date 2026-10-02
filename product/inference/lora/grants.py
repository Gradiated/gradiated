import json
import re
import urllib.parse
import urllib.request

from artifacts import NoRedirect, strict_json


def validate_endpoint(url, token):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or not token
    ):
        raise ValueError("Invalid private artifact endpoint")


def read_private(url, token, body=None, limit=65536):
    validate_endpoint(url, token)
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.build_opener(NoRedirect()).open(
        request, timeout=10
    ) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Oversized artifact response")
        return strict_json(data)


def production_targets(url, token, base_model_id):
    separator = "&" if "?" in url else "?"
    result = read_private(
        url + separator + urllib.parse.urlencode({"base_model_id": base_model_id}),
        token,
        limit=1024 * 1024,
    )["data"]
    if not isinstance(result, list):
        raise TypeError("Invalid production list")
    return result


def resolver(url, token):
    validate_endpoint(url, token)

    def resolve(name, workspace_id):
        match = re.fullmatch(r"ft-([a-f0-9-]{36})-([a-f0-9]{64})", name)
        if not match:
            raise ValueError("Invalid adapter identity")
        target = {
            "workspace_id": workspace_id,
            "version_id": match[1],
            "sha256": match[2],
        }
        grant = read_private(url, token, target)
        version = grant["version"]
        if (
            grant["workspace_id"] != workspace_id
            or version["id"] != match[1]
            or version["adapter"]["sha256"] != match[2]
        ):
            raise ValueError("Artifact grant identity mismatch")
        return grant

    return resolve
