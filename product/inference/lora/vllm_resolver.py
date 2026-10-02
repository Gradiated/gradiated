import asyncio
import http.client
import json
import os
import uuid

from vllm.lora.request import LoRARequest
from vllm.lora.resolver import LoRAResolver, LoRAResolverRegistry


class GradiatedResolver(LoRAResolver):
    def __init__(self, port):
        self.port = port

    def files(self, name, workspace_id):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=180)
        try:
            connection.request(
                "POST",
                "/internal/adapters/resolve",
                json.dumps({"name": name, "workspace_id": workspace_id}),
                {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            data = response.read(65537)
            if response.status != 200 or len(data) > 65536:
                raise RuntimeError("Adapter resolution unavailable")
            files = json.loads(data)
            if (
                not isinstance(files["path"], str)
                or not os.path.isabs(files["path"])
                or type(files["is_3d_lora_weight"]) is not bool
            ):
                raise ValueError("Invalid adapter files")
            return files
        finally:
            connection.close()

    async def resolve_lora(self, base_model_name, lora_name):
        workspace, separator, name = lora_name.partition("/")
        if not separator or not 0 < len(name) <= 300:
            return None
        try:
            if str(uuid.UUID(workspace)) != workspace:
                return None
        except ValueError:
            return None
        try:
            files = await asyncio.to_thread(self.files, name, workspace)
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
            http.client.HTTPException,
        ):
            # Keep signed URLs, credentials and internal exception text out of vLLM logs.
            raise RuntimeError("Adapter resolution unavailable") from None
        return LoRARequest(
            lora_name=lora_name,
            lora_int_id=1,
            lora_path=files["path"],
            is_3d_lora_weight=files["is_3d_lora_weight"],
        )


def register():
    if os.environ.get("LORA_ENABLED") == "true":
        LoRAResolverRegistry.register_resolver(
            "gradiated_lora", GradiatedResolver(int(os.environ["ADAPTER_PORT"]))
        )
