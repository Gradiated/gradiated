import asyncio
import importlib
import importlib.metadata
import os
import sys
import tempfile
import threading
import types
import unittest
from collections import defaultdict
from dataclasses import dataclass
from unittest import mock

from fixtures import archive, grant, settings
from loader import Loader
from server import create_server

try:
    from vllm.entrypoints.openai.models.serving import OpenAIServingModels
except ImportError:
    if os.environ.get("GRADIATED_REQUIRE_VLLM_RESOLVER") == "1":
        raise
    OpenAIServingModels = None


@dataclass
class SyntheticLoRARequest:
    lora_name: str
    lora_int_id: int
    lora_path: str
    is_3d_lora_weight: bool


def resolver_module():
    if OpenAIServingModels is not None:
        return importlib.import_module("vllm_resolver")
    modules = {
        "vllm.lora.request": types.SimpleNamespace(LoRARequest=SyntheticLoRARequest),
        "vllm.lora.resolver": types.SimpleNamespace(
            LoRAResolver=object, LoRAResolverRegistry=mock.Mock()
        ),
    }
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location(
            "synthetic_resolver",
            __file__.replace("test_resolver.py", "vllm_resolver.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class ResolverTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        payload = archive()
        self.spec = grant(payload)
        self.downloads = 0

        def fetch(spec, path, hosts):
            self.downloads += 1
            path.write_bytes(payload)

        self.loader = Loader(settings(), self.temp.name, 1, set(), fetch=fetch)
        self.name = self.loader.register_metadata(self.spec)
        self.loader.resolve = self.grant
        self.loader.ready = True
        self.loader.engine = mock.Mock(return_value=b"ok")
        self.server = create_server(self.loader, 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.module = resolver_module()
        self.resolver = self.module.GradiatedResolver(self.server.server_port)
        self.runtime_name = (
            f"{self.spec['workspace_id']}/{self.spec['version']['name']}"
        )

    def grant(self, name, workspace):
        if (
            name != self.spec["version"]["name"]
            or workspace != self.spec["workspace_id"]
        ):
            raise LookupError("Unknown version")
        return self.spec

    async def test_slashes_and_unicode_in_slugs_do_not_change_disk_paths(self):
        self.spec["version"]["name"] = "support/triage-日本語-20261002"
        self.loader.entries[self.name]["spec"] = None
        resolved = await self.resolver.resolve_lora(
            "base", f"{self.spec['workspace_id']}/{self.spec['version']['name']}"
        )
        self.assertEqual(resolved.lora_path, str(self.loader.root / self.name))

    async def test_cold_resolution_and_disk_reuse_do_not_call_the_engine(self):
        first = await self.resolver.resolve_lora("base", self.runtime_name)
        second = await self.resolver.resolve_lora("base", self.runtime_name)
        self.assertEqual(first.lora_name, self.runtime_name)
        self.assertEqual(first.lora_path, str(self.loader.root / self.name))
        self.assertEqual(first.lora_path, second.lora_path)
        self.assertFalse(first.is_3d_lora_weight)
        self.assertEqual(self.downloads, 1)
        self.loader.engine.assert_not_called()
        self.assertTrue(self.loader.entries[self.name]["pinned"])

    async def test_unknown_names_never_contact_the_loader(self):
        for name in ("base", "../adapter", self.name, "../" + self.name):
            self.assertIsNone(await self.resolver.resolve_lora("base", name))
        self.assertEqual(self.downloads, 0)

    async def test_wrong_workspace_and_version_fail_closed(self):
        for name in (
            f"01980000-0000-7000-8000-000000000002/{self.spec['version']['name']}",
            self.runtime_name + "-missing",
        ):
            with self.assertRaisesRegex(
                RuntimeError, "^Adapter resolution unavailable$"
            ):
                await self.resolver.resolve_lora("base", name)
        self.assertEqual(self.downloads, 0)
        self.loader.engine.assert_not_called()

    async def test_failed_download_can_be_retried_and_error_text_is_redacted(self):
        original = self.loader.fetch
        self.loader.fetch = mock.Mock(side_effect=OSError("secret-signed-url"))
        with (
            self.assertLogs(level="WARNING"),
            self.assertRaisesRegex(RuntimeError, "^Adapter resolution unavailable$"),
        ):
            await self.resolver.resolve_lora("base", self.runtime_name)
        self.loader.fetch = original
        self.assertIsNotNone(
            await self.resolver.resolve_lora("base", self.runtime_name)
        )
        self.assertEqual(self.downloads, 1)

    async def test_startup_registration_does_not_block_native_file_resolution(self):
        loop = asyncio.get_running_loop()

        def engine(method, path, body=None):
            if method == "POST":
                resolved = asyncio.run_coroutine_threadsafe(
                    self.resolver.resolve_lora("base", self.runtime_name), loop
                ).result(timeout=3)
                self.assertEqual(resolved.lora_path, body["lora_path"])
                self.assertEqual(body["lora_name"], self.runtime_name)
            return b"ok"

        self.loader.engine = engine
        await asyncio.wait_for(
            asyncio.to_thread(
                self.loader.prepare, self.name, self.spec["workspace_id"]
            ),
            timeout=5,
        )
        self.assertEqual(self.downloads, 1)

    @unittest.skipIf(
        OpenAIServingModels is None, "Pinned vLLM is checked in the GLM bundle"
    )
    async def test_pinned_vllm_coalesces_and_registers_native_resolution(self):
        serving = OpenAIServingModels.__new__(OpenAIServingModels)
        serving.lora_requests = {}
        serving.lora_resolvers = [self.resolver]
        serving.lora_resolver_lock = defaultdict(asyncio.Lock)
        serving.model_config = types.SimpleNamespace(model="base")
        serving.lora_id_counter = mock.Mock()
        serving.lora_id_counter.inc.return_value = 7
        serving.engine_client = types.SimpleNamespace(add_lora=mock.AsyncMock())
        first, second = await asyncio.gather(
            serving.resolve_lora(self.runtime_name),
            serving.resolve_lora(self.runtime_name),
        )
        self.assertIs(first, second)
        self.assertEqual(first.lora_int_id, 7)
        serving.engine_client.add_lora.assert_awaited_once_with(first)
        self.assertEqual(self.downloads, 1)
        self.loader.engine.assert_not_called()
        entry = next(
            entry
            for entry in importlib.metadata.entry_points(group="vllm.general_plugins")
            if entry.name == "gradiated_lora"
        )
        self.assertEqual(entry.load().__name__, "register")


if __name__ == "__main__":
    unittest.main()
