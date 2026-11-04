import { chromium } from "@playwright/test";
const out = "D:/Essity/.work/design-v22/after/";
const S = "65b1e3e1-708f-42b7-a3df-680e3022f20f";
const pages = {
  "graph": "/graph", "kho": "/kho-kien-thuc", "kho-subject": "/kho-kien-thuc?subject=" + S,
  "landing": "/", "practice": "/subjects/" + S + "/practice", "review": "/review/4efde008-2e95-4924-b65a-9e9d265db0bb",
  "stats": "/stats", "subject": "/subjects/" + S, "subject-upload": "/subjects/" + S + "/upload",
  "subjects": "/subjects", "subjects-new": "/subjects/new", "syllabus": "/subjects/" + S + "/syllabus", "today": "/today",
};
const b = await chromium.launch();
const login = await b.newContext();
const r = await login.request.post("http://localhost:3000/api/auth/login", { headers: { Origin: "http://localhost:3000" }, data: { identifier: "demo@essity.test", password: "Demo-Essity-2026" } });
console.log("login", r.status());
const state = await login.storageState();
let n = 0; const bad = [];
for (const [name, url] of Object.entries(pages)) for (const w of [1440, 390]) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 }, storageState: name === "landing" ? undefined : state });
  const p = await ctx.newPage();
  try {
    const resp = await p.goto("http://localhost:3000" + url, { waitUntil: "load", timeout: 60000 });
    await p.waitForTimeout(3000);
    await p.screenshot({ path: out + name + "-" + w + ".png", fullPage: true });
    n++; console.log(name, w, resp.status(), p.url().replace("http://localhost:3000", ""));
  } catch (e) { bad.push(name + "-" + w + ": " + e.message.split("\n")[0]); }
  await ctx.close();
}
console.log("shots", n, "bad", JSON.stringify(bad));
await b.close();
