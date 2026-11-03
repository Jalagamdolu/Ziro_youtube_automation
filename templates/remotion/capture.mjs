// Screenshot of a cited source page with the quoted passage highlighted (D-37).
// Drives Remotion's own headless Chrome over the DevTools protocol (Node's built-in WebSocket),
// because Chrome's --screenshot shortcut hangs in the worker container. No extra dependency.
// Usage: node capture.mjs <chrome> <url> <out.png> [quote]
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const [chrome, url, out, quote = ""] = process.argv.slice(2);
const WIDTH = 1080, HEIGHT = 3000;
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

await send("Emulation.setDeviceMetricsOverride", { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1,
  mobile: false });
await send("Page.navigate", { url });
await new Promise((resolve) => setTimeout(resolve, 8000)); // let the page render

// Hide fixed/sticky overlays (cookie banners, headers), then find and highlight the quote.
const script = `(() => {
  for (const el of document.querySelectorAll("body *")) {
    const pos = getComputedStyle(el).position;
    if (pos === "fixed" || pos === "sticky") el.style.setProperty("display", "none", "important");
  }
  const needle = ${JSON.stringify(quote.slice(0, 60).replace(/\s+/g, " ").trim())};
  if (!needle) return false;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const start = needle.slice(0, 24);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const host = node.parentElement;  // the element whose own text starts the quote
    if (host && node.textContent.replace(/\\s+/g, " ").includes(start)
        && host.innerText.replace(/\\s+/g, " ").includes(needle)) {
      host.style.setProperty("background", "#FFE066", "important");
      host.style.setProperty("outline", "8px solid #FF7700", "important");
      host.scrollIntoView({ block: "start" });
      window.scrollBy(0, -320);
      return true;
    }
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
