import { WizardError } from "./errors.js";
import { isRecord } from "./guards.js";

const stringEnd = (text: string, start: number): number => {
  let index = start + 1;

  while (index < text.length) {
    const character = text.charAt(index);
    if (character === '"') return index + 1;
    index += character === "\\" ? 2 : 1;
  }

  return text.length;
};

const withoutTrailingComma = (output: string): string => {
  const trimmed = output.trimEnd();

  return trimmed.endsWith(",")
    ? trimmed.slice(0, -1) + output.slice(trimmed.length)
    : output;
};

export const stripJsonc = (text: string): string => {
  let output = "";
  let index = 0;

  while (index < text.length) {
    const character = text.charAt(index);
    const next = text.charAt(index + 1);

    if (character === '"') {
      const end = stringEnd(text, index);
      output += text.slice(index, end);
      index = end;
    } else if (character === "/" && next === "/") {
      const newline = text.indexOf("\n", index);
      index = newline === -1 ? text.length : newline;
    } else if (character === "/" && next === "*") {
      const close = text.indexOf("*/", index + 2);
      index = close === -1 ? text.length : close + 2;
    } else {
      if (character === "}" || character === "]") {
        output = withoutTrailingComma(output);
      }
      output += character;
      index += 1;
    }
  }

  return output;
};

export const parseJsonc = (
  path: string,
  text: string,
): Record<string, unknown> => {
  const json = stripJsonc(text);
  if (json.trim().length === 0) return {};

  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch (error) {
    throw new WizardError(`${path} is not valid JSONC. Fix or move it.`, {
      cause: error,
    });
  }

  if (!isRecord(parsed)) {
    throw new WizardError(`${path} does not contain a JSON object.`);
  }

  return parsed;
};
