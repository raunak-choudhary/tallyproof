// RFC 8785 canonical JSON, with the same safety rules as the Python core: no
// non-integer numbers, integers within 0..2^53-1, and no lone surrogates.
import canonicalizeJson from "canonicalize";

export const MAX_SAFE_INTEGER = Number.MAX_SAFE_INTEGER; // 2^53 - 1

const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/;

export class CanonicalizationError extends Error {}

function check(value: unknown, path: string): void {
  if (value === null || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isInteger(value)) {
      throw new CanonicalizationError(`${path}: floats are not allowed; use a decimal string`);
    }
    if (value < 0 || value > MAX_SAFE_INTEGER) {
      throw new CanonicalizationError(`${path}: integer ${value} is outside 0..2**53-1`);
    }
    return;
  }
  if (typeof value === "string") {
    if (LONE_SURROGATE.test(value)) {
      throw new CanonicalizationError(`${path}: string is not valid Unicode`);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => check(item, `${path}[${index}]`));
    return;
  }
  if (typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      check(key, `${path}.<key>`);
      check(item, `${path}.${key}`);
    }
    return;
  }
  throw new CanonicalizationError(`${path}: unsupported type ${typeof value}`);
}

/** Serialize a JSON value to RFC 8785 canonical text. */
export function canonicalize(value: unknown): string {
  check(value, "$");
  const text = canonicalizeJson(value);
  if (text === undefined) throw new CanonicalizationError("$: value cannot be serialized");
  return text;
}
