// Renders a share image per page in src/og-pages.ts from the OG template.
// Run from product/website: pnpm exec tsx scripts/og-images.mjs <template.png>
// (the template is the 2400x1260 design with its strip labels in place).
import { mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { ogImageFor, ogPages } from "../src/og-pages.ts";

const template = process.argv[2];
if (!template) throw new Error("Pass the template PNG path.");

const require = createRequire(import.meta.url);
const { chromium } = require(
  require.resolve("playwright", {
    paths: [process.cwd(), `${process.cwd()}/..`],
  }),
);

const background = `data:image/png;base64,${readFileSync(template).toString("base64")}`;
const escape = (text) =>
  text.replace(
    /[&<>]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c],
  );

// The template's labels sit in the strip at x 2177-2205; that column is
// painted over and the two labels are set again in the same type.
const page = (name, line) => `<!doctype html>
<link rel="preconnect" href="https://fonts.gstatic.com" />
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@600&display=block" rel="stylesheet" />
<style>
  html, body { margin: 0; width: 2400px; height: 1260px; overflow: hidden; background: #151515; }
  .bg { position: absolute; inset: 0; background: url(${background}) 0 0 / 2400px 1260px; }
  .clear { position: absolute; left: 2168px; width: 42px; top: 20px; bottom: 20px; background: #151515; }
  .label { position: absolute; left: 2176px; width: 30px; color: #e9e9e9;
    font: 600 28px/30px Barlow, sans-serif; letter-spacing: 0.09em; text-transform: uppercase;
    writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; }
  .name { top: 47px; }
  .line { bottom: 48px; }
</style>
<div class="bg"></div><div class="clear"></div>
<div class="label name">/${escape(name)}</div>
<div class="label line">${escape(line)}</div>`;

mkdirSync("public/og", { recursive: true });
const browser = await chromium.launch();
const tab = await browser.newPage({ viewport: { width: 2400, height: 1260 } });
for (const [path, [name, line]] of Object.entries(ogPages)) {
  await tab.setContent(page(name, line), { waitUntil: "networkidle" });
  await tab.evaluate(() => document.fonts.ready);
  const out = `public${ogImageFor(path)}`;
  const shot = await tab.screenshot({ type: "jpeg", quality: 90 });
  // Downscale to 1200x630 in the browser for a clean resample.
  const small = await tab.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/jpeg;base64,${b64}`;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = 1200;
    c.height = 630;
    const x = c.getContext("2d");
    x.imageSmoothingQuality = "high";
    x.drawImage(img, 0, 0, 1200, 630);
    return c.toDataURL("image/jpeg", 0.86).split(",")[1];
  }, shot.toString("base64"));
  await import("node:fs").then((fs) =>
    fs.writeFileSync(out, Buffer.from(small, "base64")),
  );
  console.log(out);
}
await browser.close();
