import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";

export const QWEN_REPO = "Qwen/Qwen3-0.6B";
export const QWEN_REVISION = "c1899de289a04d12100db370d81485cdf75e47ca";

const sha256 = (bytes: Uint8Array) =>
  createHash("sha256").update(bytes).digest("hex");

type Member = { name: string; body: Buffer; type?: string };

const header = ({ name, body, type = "0" }: Member) => {
  const block = Buffer.alloc(512);
  block.write(name, 0, 100, "utf8");
  block.write("0000644\0", 100);
  block.write("0000000\0", 108);
  block.write("0000000\0", 116);
  block.write(body.length.toString(8).padStart(11, "0") + "\0", 124);
  block.write("00000000000\0", 136);
  block.write("        ", 148);
  block.write(type, 156);
  block.write("ustar\0", 257);
  block.write("00", 263);
  let sum = 0;
  for (const byte of block) sum += byte;
  block.write(sum.toString(8).padStart(6, "0") + "\0 ", 148);
  return block;
};

export const tarGz = (members: readonly Member[]) =>
  gzipSync(
    Buffer.concat([
      ...members.flatMap((member) => [
        header(member),
        member.body,
        Buffer.alloc((512 - (member.body.length % 512)) % 512),
      ]),
      Buffer.alloc(1024),
    ]),
  );

/** A grad.artifact/1 bundle as grad-trainer writes it, with manifest overrides. */
export const gradBundle = (
  files: Record<string, Buffer>,
  {
    format = "peft_lora",
    manifest = {},
    extra = [],
  }: {
    format?: string;
    manifest?: Record<string, unknown>;
    extra?: Member[];
  } = {},
) => {
  const body = Buffer.from(
    JSON.stringify({
      schema: "grad.artifact/1",
      kind: "final",
      format,
      format_version: 1,
      recipe_kind: format === "cartridge" ? "cartridge" : "sft",
      base_model: "qwen/qwen3-0.6b",
      base_model_repo: QWEN_REPO,
      base_model_revision: QWEN_REVISION,
      deployable: true,
      created_by: { name: "grad-trainer", version: "0.2.0" },
      files: Object.fromEntries(
        Object.entries(files).map(([name, bytes]) => [name, sha256(bytes)]),
      ),
      ...manifest,
    }),
  );
  const bytes = tarGz(
    [
      { name: "manifest.json", body },
      ...Object.entries(files).map(([name, file]) => ({ name, body: file })),
      ...extra,
    ].sort((left, right) => left.name.localeCompare(right.name)),
  );
  return { bytes, sha256: sha256(bytes), sizeBytes: bytes.length };
};
