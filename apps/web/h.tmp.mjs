import { chromium } from "@playwright/test";
import fs from "node:fs";
const BASE="http://localhost:3100";
const [email, password] = fs.readFileSync("../../.work/D1-SELFTEST-CORE/account.txt","utf8").trim().split("\n");
const sid=fs.readFileSync("../../.work/D1-SELFTEST-CORE/sid.txt","utf8");
const b = await chromium.launch();
const c = await b.newContext({viewport:{width:1440,height:900}});
const p = await c.newPage();
await p.goto(BASE+"/login"); await p.getByLabel(/email/i).fill(email); await p.getByLabel(/mật khẩu/i).first().fill(password); await p.keyboard.press("Enter");
await p.waitForURL(u=>!u.pathname.startsWith("/login"));
for (const u of ["/today","/subjects","/stats","/subjects/"+sid,"/subjects/"+sid+"/syllabus","/subjects/"+sid+"/practice"]) {
  await p.goto(BASE+u,{waitUntil:"networkidle"}); await p.waitForTimeout(500);
  console.log(u.slice(0,40), await p.evaluate(()=>[document.documentElement.scrollHeight, document.body.scrollHeight, Math.max(...[...document.querySelectorAll("body *")].map(e=>e.getBoundingClientRect().bottom+scrollY|0))]));
}
await b.close();
