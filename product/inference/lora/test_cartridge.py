import json
import struct
import tempfile
import unittest
from pathlib import Path

import cartridge
from fixtures import (
    GRAD_SOURCE,
    cartridge_file,
    cartridge_grant,
    cartridge_model_config,
    grad_bundle,
)


class CartridgeFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = cartridge_model_config()

    def materialize(self, payload, spec=None):
        spec = spec or cartridge_grant(payload)
        fetches = []

        def fetch(_spec, path, _hosts):
            fetches.append(path)
            path.write_bytes(payload)

        directory, disk = cartridge.materialize(
            spec, self.root, 1024 * 1024, set(), self.config, fetch
        )
        return directory, disk, fetches

    def test_valid_cartridge_is_stored_with_a_manifest_and_reused(self):
        payload = cartridge_file()
        spec = cartridge_grant(payload)
        directory, disk, fetches = self.materialize(payload, spec)

        self.assertEqual((directory / cartridge.FILE).read_bytes(), payload)
        self.assertEqual(
            {path.name for path in directory.iterdir()},
            {cartridge.FILE, ".verified.json"},
        )
        self.assertEqual(disk, sum(path.stat().st_size for path in directory.iterdir()))

        _directory, _disk, again = self.materialize(payload, spec)
        self.assertEqual((len(fetches), len(again)), (1, 0))

    def test_corrupt_cached_file_is_downloaded_again(self):
        payload = cartridge_file()
        spec = cartridge_grant(payload)
        directory, _disk, _fetches = self.materialize(payload, spec)
        (directory / cartridge.FILE).write_bytes(payload[:-1] + b"\1")

        _directory, _disk, fetches = self.materialize(payload, spec)

        self.assertEqual(len(fetches), 1)
        self.assertEqual((directory / cartridge.FILE).read_bytes(), payload)

    def test_size_and_checksum_must_match_the_task_version(self):
        payload = cartridge_file()
        spec = cartridge_grant(payload)
        spec["version"]["adapter"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.materialize(payload, spec)

        spec = cartridge_grant(payload)
        spec["version"]["adapter"]["size_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.materialize(payload, spec)

        self.assertEqual(list(self.root.iterdir()), [])

    def test_shapes_must_match_the_model_and_the_task_version(self):
        cases = [
            (cartridge_file(hidden=5), {"hidden_size": 4}),
            (cartridge_file(tokens=2), {"num_tokens": 3}),
            (cartridge_file(slots=False), {"has_slot_token_ids": True}),
            (cartridge_file(), {"has_slot_token_ids": False}),
        ]
        for payload, change in cases:
            spec = cartridge_grant(payload)
            spec["version"]["adapter"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.materialize(payload, spec)

    def test_metadata_must_name_the_format_placement_and_separator(self):
        cases = [
            ({"placement": "system_prompt_start"}, "\n\n"),
            ({"format": "gradiated.cartridge/1", "placement": "suffix"}, "\n\n"),
            ({"format": "gradiated.cartridge/1", "separator": "\n"}, "\n\n"),
            ({"format": "gradiated.cartridge/1"}, "\n"),
        ]
        for metadata, separator in cases:
            payload = cartridge_file(metadata=metadata)
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                self.materialize(payload, cartridge_grant(payload, separator=separator))

        payload = cartridge_file(
            metadata={"format": "gradiated.cartridge/1", "separator": "\n"}
        )
        self.materialize(payload, cartridge_grant(payload, separator="\n"))

    def test_non_finite_embeddings_and_out_of_vocabulary_slots_are_rejected(self):
        for bits in (0x7F80, 0xFF80, 0x7FC1):
            values = struct.pack("<12H", *([0x3F80] * 11 + [bits]))
            with (
                self.subTest(bits=hex(bits)),
                self.assertRaisesRegex(ValueError, "finite"),
            ):
                self.materialize(cartridge_file(values=values))

        largest_finite = struct.pack("<12H", *([0x7F7F, 0xFF7F, 0x0080, 0x8000] * 3))
        self.materialize(cartridge_file(values=largest_finite))

        payload = bytearray(cartridge_file())
        payload[-8:] = struct.pack("<q", 32)
        with self.assertRaisesRegex(ValueError, "vocabulary"):
            self.materialize(bytes(payload))

    def test_header_rejects_extra_tensors_overlaps_and_trailing_bytes(self):
        valid = cartridge_file()
        header_size = struct.unpack("<Q", valid[:8])[0]
        header = json.loads(valid[8 : 8 + header_size])
        body = valid[8 + header_size :]
        extra = dict(
            header, bias={"dtype": "BF16", "shape": [1], "data_offsets": [0, 2]}
        )
        overlapping = json.loads(json.dumps(header))
        overlapping["slot_token_ids"]["data_offsets"] = [0, 24]
        for value in (extra, overlapping):
            encoded = json.dumps(value).encode()
            payload = struct.pack("<Q", len(encoded)) + encoded + body
            with self.subTest(value=sorted(value)), self.assertRaises(ValueError):
                self.materialize(payload)

        with self.assertRaisesRegex(ValueError, "Trailing"):
            self.materialize(valid + b"\0")
        with self.assertRaises(ValueError):
            self.materialize(struct.pack("<Q", 2 * 1024 * 1024) + b"{}")

    def test_metadata_is_checked_against_the_pinned_model_config(self):
        adapter = cartridge_grant(cartridge_file())["version"]["adapter"]
        cartridge.validate_metadata(adapter, {"text_config": self.config})

        for change in (
            {"num_tokens": 64},
            {"num_tokens": 0},
            {"hidden_size": 8},
            {"placement": "suffix"},
            {"separator": "x" * 65},
            {"has_slot_token_ids": 1},
            {"has_slot_token_ids": False},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                cartridge.validate_metadata({**adapter, **change}, self.config)
        with self.assertRaises(ValueError):
            cartridge.validate_metadata(adapter, {"num_hidden_layers": 2})

    def test_resolved_files_name_the_kind_path_and_identity(self):
        payload = cartridge_file()
        spec = cartridge_grant(payload)
        directory, _disk, _fetches = self.materialize(payload, spec)

        self.assertEqual(
            cartridge.resolved_files(directory, spec["version"]["adapter"]),
            {
                "kind": "cartridge",
                "path": str(directory / cartridge.FILE),
                "sha256": spec["version"]["adapter"]["sha256"],
                "num_tokens": 3,
            },
        )


class GradCartridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def materialize(self, bundle, spec):
        fetches = []

        def fetch(_spec, path, _hosts):
            fetches.append(path)
            path.write_bytes(bundle)

        directory, _disk = cartridge.materialize(
            spec, self.root, 1024 * 1024, set(), cartridge_model_config(), fetch
        )
        return directory, fetches

    def grant(self, bundle):
        spec = cartridge_grant(bundle)
        spec["version"]["adapter"]["source"] = GRAD_SOURCE
        return spec

    def test_a_grad_cartridge_bundle_is_extracted_verified_and_reused(self):
        payload = cartridge_file()
        bundle = grad_bundle({cartridge.FILE: payload}, adapter_format="cartridge")
        spec = self.grant(bundle)

        directory, fetches = self.materialize(bundle, spec)

        self.assertEqual((directory / cartridge.FILE).read_bytes(), payload)
        self.assertEqual(
            {path.name for path in directory.iterdir()},
            {cartridge.FILE, ".verified.json"},
        )
        _directory, again = self.materialize(bundle, spec)
        self.assertEqual((len(fetches), len(again)), (1, 0))

    def test_a_grad_cartridge_bundle_must_match_its_manifest(self):
        payload = cartridge_file()
        bundle = grad_bundle(
            {cartridge.FILE: payload},
            adapter_format="cartridge",
            manifest={"files": {cartridge.FILE: "0" * 64}},
        )
        with self.assertRaises(ValueError):
            self.materialize(bundle, self.grant(bundle))
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
