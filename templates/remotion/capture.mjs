// Screenshot of a cited source page with the quoted passage highlighted (D-37).
// Drives Remotion's own headless Chrome over the DevTools protocol (Node's built-in WebSocket),
// because Chrome's --screenshot shortcut hangs in the worker container. No extra dependency.
// Usage: node capture.mjs <chrome> <url> <out.png> [quote]
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const [chrome, url, out, quote = ""] = process.argv.slice(2);
// A narrow 640 px window at 1.6875x: the page becomes a 1080 px image whose text reads on a phone.
const WIDTH = 640, HEIGHT = 1800, SCALE = 1.6875;
const proc = spawn(chrome, ["--no-sandbox", "--disable-gpu", "--hide-scrollbars",
  "--disable-dev-shm-usage", "--remote-debugging-port=0", `--window-size=${WIDTH},${HEIGHT}`,
  "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
const fail = (why) => { console.error(why); proc.kill("SIGKILL"); process.exit(2); };
setTimeout(() => fail("timed out"), 45000);

const devtools = await new Promise((resolve) => {
  let log = "";
  proc.stderr.on("data", (chunk) => {
    log += chunk;
    const found = log.match(/DevTools listening on (ws:\/\/\S+)/);
    if (found) resolve(found[1]);
  });
});
const port = new URL(devtools).port;
const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve) => { ws.onopen = resolve; });
let next = 0;
const waiting = new Map();
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (waiting.has(message.id)) { waiting.get(message.id)(message); waiting.delete(message.id); }
};
const send = (method, params = {}) => new Promise((resolve) => {
  next += 1;
  waiting.set(next, resolve);
  ws.send(JSON.stringify({ id: next, method, params }));
});

await send("Emulation.setDeviceMetricsOverride", { width: WIDTH, height: HEIGHT,
  deviceScaleFactor: SCALE, mobile: false });  // narrow + zoomed; "mobile" makes some sites hide articles
await send("Page.navigate", { url });
await new Promise((resolve) => setTimeout(resolve, 8000)); // let the page render

// Hide fixed/sticky overlays (cookie banners, headers) and adverts, then find and highlight the
// quote. The honesty line (D-59): ads, cookie banners and popups may be hidden, like overlays;
// the article text, the quoted passage and its highlight are never altered. Nothing is ever
// edited or added, only hidden, and never the quote, anything containing it or anything in it.
const script = `(() => {
  for (const el of document.querySelectorAll("body *")) {
    const pos = getComputedStyle(el).position;
    if (pos === "fixed" || pos === "sticky") el.style.setProperty("display", "none", "important");
  }
  const needle = ${JSON.stringify(quote.slice(0, 60).replace(/\s+/g, " ").trim())};
  // The smallest element whose text contains the quote (links inside the sentence are fine).
  const norm = (text) => text.replace(/\\s+/g, " ");  // doubled backslash: inside a template string
  let best = null;
  for (const el of needle ? document.querySelectorAll("body *") : []) {
    const text = el.textContent || "";
    if (text.length >= needle.length && (!best || text.length < best.textContent.length)
        && norm(text).includes(needle)) best = el;
  }
  const AD_TAG = /(^|-)(ad|ads|advert|advertisement|placement|sponsor|sponsored|promo|survey)(-|$)/i;
  const AD_NAME = /^(ad|ads|adsbygoogle|advert|advertisement|ad-slot|sponsor|sponsored|promo|promoted|cookie|cookies|consent|gdpr|newsletter|popup|modal|survey)([-_].*)?$/i;
  for (const el of document.querySelectorAll("body *")) {
    if (best && (el.contains(best) || best.contains(el))) continue;  // the quote stays as published
    const names = [...el.classList, el.id].filter(Boolean);
    const label = (el.getAttribute("aria-label") || "") + " " + (el.getAttribute("role") || "");
    if (el.tagName === "IFRAME" || el.tagName === "INS" || AD_TAG.test(el.tagName)
        || names.some((n) => AD_NAME.test(n)) || /advert|sponsor|alertdialog/i.test(label)) {
      el.style.setProperty("display", "none", "important");
    }
  }
  if (best) {
    best.style.setProperty("background", "#FFE066", "important");
    best.style.setProperty("outline", "8px solid #FF7700", "important");
    best.scrollIntoView({ block: "start" });
    window.scrollBy(0, -180);
    return true;
  }
  return false;
})()`;
const found = await send("Runtime.evaluate", { expression: script, returnByValue: true });
await new Promise((resolve) => setTimeout(resolve, 800));
const shot = await send("Page.captureScreenshot", { format: "png" });
if (!shot.result || !shot.result.data) fail("no screenshot");
writeFileSync(out, Buffer.from(shot.result.data, "base64"));
console.log(JSON.stringify({ highlighted: Boolean(found.result && found.result.result && found.result.result.value) }));
ws.close();
proc.kill("SIGKILL");
process.exit(0);
