import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from grants import host_identity, read_private


class HostCredentialTests(unittest.TestCase):
    def identity(self):
        return {
            "instance_id": "01980000-0000-7000-8000-000000000001",
            "nomad_node_id": "01980000-0000-7000-8000-000000000002",
            "token": "a" * 43,
        }

    def test_reads_existing_identity_and_rejects_invalid_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "identity.json"
            identity = self.identity()
            path.write_text(json.dumps(identity))
            self.assertEqual(host_identity(path), identity)
            for override in (
                {"token": "short"},
                {"instance_id": "bad"},
                {"nomad_node_id": "bad"},
            ):
                path.write_text(json.dumps({**identity, **override}))
                with self.assertRaises(ValueError):
                    host_identity(path)

    def test_private_requests_send_existing_host_identity(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"data": []}'
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch("urllib.request.build_opener", return_value=opener):
            self.assertEqual(
                read_private("https://api.example/internal", self.identity()),
                {"data": []},
            )
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer " + "a" * 43)
        self.assertEqual(
            request.get_header("X-gradiated-instance-id"),
            self.identity()["instance_id"],
        )
        self.assertEqual(
            request.get_header("X-gradiated-nomad-node-id"),
            self.identity()["nomad_node_id"],
        )
