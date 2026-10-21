// Reads the colour tokens of app/globals.css and computes WCAG contrast, for the token tests.
// Anything it cannot resolve throws: a pair that silently drops out would pass without being
// checked (review plan #3).
import { readFileSync } from "node:fs";
import path from "node:path";

export type Mode = "light" | "dark";
export type Tokens = Record<string, string>;
type Rgba = [number, number, number, number];

const CSS = readFileSync(path.resolve(import.meta.dirname, "../app/globals.css"), "utf-8");

/** The body of the first rule whose selector list is exactly `selector`. */
export function block(selector: string, css = CSS): string {
  const start = css.indexOf(`${selector} {`);
  if (start === -1) throw new Error(`no rule for ${selector}`);
  let depth = 0;
  for (let i = css.indexOf("{", start); i < css.length; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}" && --depth === 0) return css.slice(css.indexOf("{", start) + 1, i);
  }
  throw new Error(`unclosed rule for ${selector}`);
}

export function declarations(body: string): Tokens {
  const out: Tokens = {};
  const withoutComments = body.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const match of withoutComments.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    out[match[1]] = match[2].trim();
  }
  return out;
}

export const SELECTORS = {
  light: ':root,\n[data-tone="light"]',
  dark: ':root[data-theme="dark"],\n[data-tone="dark"]',
  // The OS-dark copy of the dark palette, nested in @media (prefers-color-scheme: dark).
  osDark: ':root:not([data-theme="light"])',
} as const;

export function palette(mode: Mode): Tokens {
  return declarations(block(mode === "light" ? SELECTORS.light : SELECTORS.dark));
}

export function osDarkPalette(): Tokens {
  // @custom-variant has its own @media block first: take the one that holds the palette.
  const media = "@media (prefers-color-scheme: dark)";
  for (let at = CSS.indexOf(media); at !== -1; at = CSS.indexOf(media, at + 1)) {
    const body = block(media, CSS.slice(at));
    if (body.includes(`${SELECTORS.osDark} {`)) return declarations(block(SELECTORS.osDark, body));
  }
  throw new Error("no OS-dark palette block");
}

function hex(value: string): Rgba {
  const m = /^#([0-9a-f]{6})$/i.exec(value);
  if (!m) throw new Error(`not a 6-digit hex colour: ${value}`);
  const n = Number.parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1];
}

/** A token's colour, following var() and color-mix(in srgb, <colour> N%, transparent). */
export function colour(tokens: Tokens, name: string, seen: string[] = []): Rgba {
  if (seen.includes(name)) throw new Error(`cycle: ${[...seen, name].join(" → ")}`);
  const value = tokens[name];
  if (value === undefined) throw new Error(`token ${name} is not declared`);
  return parse(tokens, value, [...seen, name]);
}

function parse(tokens: Tokens, value: string, seen: string[]): Rgba {
  const ref = /^var\((--[\w-]+)\)$/.exec(value);
  if (ref) return colour(tokens, ref[1], seen);
  const mix = /^color-mix\(in srgb,\s*(.+?)\s+(\d+(?:\.\d+)?)%,\s*transparent\)$/.exec(value);
  if (mix) {
    const [r, g, b, a] = parse(tokens, mix[1], seen);
    return [r, g, b, a * (Number(mix[2]) / 100)];
  }
  return hex(value);
}

function over(top: Rgba, bottom: Rgba): Rgba {
  const a = top[3];
  return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat(1) as Rgba;
}

function luminance([r, g, b]: Rgba): number {
  const lin = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/**
 * Contrast of `fg` on `bg`. A translucent background (the dark highlighter) is laid on
 * `base` first, which must then be opaque.
 */
export function contrast(tokens: Tokens, fg: string, bg: string, base?: string): number {
  let back = colour(tokens, bg);
  if (back[3] < 1) {
    if (!base) throw new Error(`${bg} is translucent: name the surface under it`);
    back = over(back, colour(tokens, base));
  }
  const front = over(colour(tokens, fg), back);
  const [hi, lo] = [luminance(front), luminance(back)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
