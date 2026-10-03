import http.client
import json
import logging
import time
import urllib.error
import urllib.parse
from pathlib import Path
from socket import gaierror
from ssl import SSLEOFError

LIMIT = 256 * 1024 * 1024


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("Training artifact transfer deadline exceeded")
    return seconds


def timeout(deadline):
    return min(40, remaining(deadline))


def retry_reason(error):
    if isinstance(error, urllib.error.HTTPError):
        return "http" if error.code in (408, 429, 500, 502, 503, 504) else None
    if isinstance(error, gaierror):
        return "dns"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (ConnectionError, SSLEOFError, http.client.IncompleteRead)):
        return "connection"
    return None


def read_body(response, socket, target, deadline):
    expected = response.getheader("Content-Length")
    expected = int(expected) if expected is not None else None
    if expected is not None and not 0 <= expected <= LIMIT:
        raise ValueError("Artifact exceeds transfer limit")
    size = 0
    while not response.isclosed():
        socket.settimeout(timeout(deadline))
        chunk = response.read1(1024 * 1024)
        remaining(deadline)
        if not chunk:
            break
        size += len(chunk)
        if size > LIMIT:
            raise ValueError("Artifact exceeds transfer limit")
        if target is not None:
            target.write(chunk)
    if expected is not None and size != expected:
        raise ConnectionError("Artifact response ended before its declared size")


def exchange(url, destination, upload, deadline):
    connection = http.client.HTTPSConnection(
        url.hostname, url.port, timeout=timeout(deadline)
    )
    try:
        connection.connect()
        socket = connection.sock
        path = urllib.parse.urlunsplit(("", "", url.path or "/", url.query, ""))
        socket.settimeout(timeout(deadline))
        if upload is None:
            connection.request("GET", path)
        else:
            size = upload.stat().st_size
            if size > LIMIT:
                raise ValueError("Artifact exceeds transfer limit")
            connection.putrequest("PUT", path)
            connection.putheader("Content-Length", str(size))
            connection.endheaders()
            sent = 0
            with upload.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    remaining(deadline)
                    sent += len(chunk)
                    if sent > size:
                        raise ValueError("Upload changed size")
                    socket.settimeout(timeout(deadline))
                    connection.send(chunk)
            if sent != size:
                raise ValueError("Upload changed size")
        socket.settimeout(timeout(deadline))
        with connection.getresponse() as response:
            if not 200 <= response.status < 300:
                raise urllib.error.HTTPError(
                    f"https://{url.hostname}",
                    response.status,
                    "Artifact request failed",
                    {},
                    None,
                )
            if destination is None:
                read_body(response, socket, None, deadline)
            else:
                with destination.open("wb") as target:
                    read_body(response, socket, target, deadline)
    finally:
        connection.close()


def transfer(url, destination=None, upload=None):
    url = urllib.parse.urlsplit(url)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Artifact URL must use HTTPS without credentials")
    if (destination is None) == (upload is None):
        raise ValueError("Choose download or upload")
    destination = Path(destination) if destination is not None else None
    upload = Path(upload) if upload is not None else None
    deadline = time.monotonic() + 120
    for attempt in range(3):
        try:
            exchange(url, destination, upload, deadline)
            return
        except (OSError, http.client.IncompleteRead) as error:
            reason = retry_reason(error)
            if reason is None or attempt == 2 or time.monotonic() >= deadline:
                raise
            logging.getLogger(__name__).warning(
                json.dumps(
                    {
                        "event": "trainer_transfer_retry",
                        "operation": "upload" if upload is not None else "download",
                        "reason": reason,
                        "attempt": attempt + 1,
                    }
                )
            )
            time.sleep(min(1, remaining(deadline)))
