const fs = require("node:fs");
const path = require("node:path");

const CATALOG_PATH = path.resolve(
  __dirname,
  "../../packages/contracts/src/model-catalog.ts",
);

const FALLBACK_MODELS = {
  OPUS_MODEL: "anthropic/claude-opus-5-5",
  SONNET_MODEL: "anthropic/claude-sonnet-5-5",
  GPT_MODEL: "openai/gpt-6.1-sol",
};

function readCatalogIds() {
  if (!fs.existsSync(CATALOG_PATH)) {
    return [];
  }
  const source = fs.readFileSync(CATALOG_PATH, "utf8");
  const start = source.indexOf("export const MODEL_CATALOG");
  const end = source.indexOf("as const satisfies readonly CatalogEntry[]");
  const section =
    start !== -1 && end !== -1 ? source.slice(start, end) : source;
  return [...section.matchAll(/\bid:\s*"([^"]+)"/g)].map((m) => m[1]);
}

function loadDocModels() {
  const ids = readCatalogIds();
  const find = (pattern, fallback) =>
    ids.find((id) => pattern.test(id)) ?? fallback;

  return {
    OPUS_MODEL: find(/^anthropic\/claude-opus-/, FALLBACK_MODELS.OPUS_MODEL),
    SONNET_MODEL: find(
      /^anthropic\/claude-sonnet-/,
      FALLBACK_MODELS.SONNET_MODEL,
    ),
    GPT_MODEL: find(/^openai\/gpt-/, FALLBACK_MODELS.GPT_MODEL),
  };
}

const DOC_MODELS = loadDocModels();

function substituteDocModels(value) {
  if (typeof value !== "string" || !value.includes("{{")) return value;
  return value
    .replaceAll("{{OPUS_MODEL}}", DOC_MODELS.OPUS_MODEL)
    .replaceAll("{{SONNET_MODEL}}", DOC_MODELS.SONNET_MODEL)
    .replaceAll("{{GPT_MODEL}}", DOC_MODELS.GPT_MODEL);
}

function walkNode(node) {
  if (!node || typeof node !== "object") return;
  if (typeof node.value === "string") {
    node.value = substituteDocModels(node.value);
  }
  if (Array.isArray(node.attributes)) {
    for (const attr of node.attributes) {
      if (attr && typeof attr.value === "string") {
        attr.value = substituteDocModels(attr.value);
      }
    }
  }
  if (Array.isArray(node.children)) {
    for (const child of node.children) {
      walkNode(child);
    }
  }
}

function remarkDocsModels() {
  return (tree) => {
    walkNode(tree);
  };
}

module.exports = {
  DOC_MODELS,
  OPUS_MODEL: DOC_MODELS.OPUS_MODEL,
  SONNET_MODEL: DOC_MODELS.SONNET_MODEL,
  GPT_MODEL: DOC_MODELS.GPT_MODEL,
  loadDocModels,
  substituteDocModels,
  remarkDocsModels,
};
