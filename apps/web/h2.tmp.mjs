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
await p.goto(BASE+"/subjects/"+sid,{waitUntil:"networkidle"}); await p.waitForTimeout(800);
console.log(await p.evaluate(()=>{let e=[...document.querySelectorAll("li")].find(x=>x.getBoundingClientRect().bottom+scrollY>4000)||document.querySelector("ul.list-none");const out=[];while(e&&e!==document.body){const s=getComputedStyle(e);out.push(e.tagName+"."+(e.className+"").slice(0,50)+" ov="+s.overflowY+" h="+s.height+" mh="+s.maxHeight+" pos="+s.position);e=e.parentElement}return out.join("
")}));
await b.close();
