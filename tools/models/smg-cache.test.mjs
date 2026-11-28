import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const names = ["glm-5-3-flash-sglang", "deepseek-v4-1-flash-sglang", "kimi-k31-pro", "qwen3-8b-sglang"];
const dockerfiles = names.map((name) => readFileSync(`product/inference/bundles/${name}/Dockerfile`, "utf8"));
const compiler = (text) => text.slice(text.indexOf("FROM ubuntu:24.04", text.indexOf("AS dependencies")), text.indexOf("FROM dependencies AS router"));

test("SMG compilation is independent of the SGLang environment and runtime inputs", () => {
  for (const [i, text] of dockerfiles.entries()) {
    const build = compiler(text);
    assert.ok(build.startsWith("FROM ubuntu:"), names[i]);
    assert.match(build, /AS smg-python/);
    assert.match(build, /FROM smg-python AS smg-source/);
    assert.match(build, /FROM smg-source AS smg-compiler/);
    assert.doesNotMatch(build, /FROM dependencies|runtimes\/|lmsysorg\/sglang|flashinfer/);
    assert.doesNotMatch(build, /COPY .*\/patches \/|COPY .*\/requirements.txt /);
    assert.match(build, /cargo test --locked --release -p smg --lib middleware::concurrency::tests/);
    assert.match(build, /maturin build --locked --release .* --out \/smg-wheels/);
    assert.match(text, /FROM dependencies AS router\nCOPY --from=smg-compiler \/smg-wheels \/smg-wheels/);
    assert.match(text, /FROM router AS package/);
    if (i !== 2) assert.match(text, /uv pip check --python/);
  }
});

test("matching compiler graphs deduplicate while base and LoRA patches stay separate", () => {
  assert.equal(compiler(dockerfiles[0]), compiler(dockerfiles[1]));
  assert.equal(compiler(dockerfiles[0]), compiler(dockerfiles[3]));
  const source = (text) => compiler(text).split("FROM smg-source AS smg-compiler")[0];
  assert.equal(source(dockerfiles[0]), source(dockerfiles[2]));
  assert.match(compiler(dockerfiles[0]), /COPY .*\/smg-lora \/tmp\/smg-lora/);
  assert.match(compiler(dockerfiles[0]), /worker::registry::tests::unknown_models/);
  assert.doesNotMatch(compiler(dockerfiles[2]), /smg-lora|sglang-lora-/);
  assert.match(compiler(dockerfiles[2]), /id=sglang-base-smg-target/);
});

test("GLM's native hash build owns its compiler and OpenSSL headers", () => {
  const router = dockerfiles[0].split("FROM dependencies AS router")[1].split("FROM router AS package")[0];
  const install = router.indexOf("apt-get install -y --no-install-recommends build-essential libssl-dev");
  const build = router.indexOf("/bundle/python/bin/python3 /tmp/sglang-patches/build-native-hash.py");
  assert.ok(install >= 0 && build > install);
});
