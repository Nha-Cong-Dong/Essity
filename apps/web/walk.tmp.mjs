import { chromium } from "@playwright/test";
import fs from "node:fs";
const BASE = "http://localhost:3100";
const OUT = "D:/Essity/.claude/worktrees/L2/.work/D1-SELFTEST-CORE/ev";
const [email, password] = fs.readFileSync("D:/Essity/.claude/worktrees/L2/.work/D1-SELFTEST-CORE/account.txt","utf8").trim().split("\n");
const pages = process.argv.slice(2);
const browser = await chromium.launch();
for (const [w,h,name] of [[1440,900,"d"],[390,844,"m"]]) for (const scheme of ["light","dark"]) {
  const ctx = await browser.newContext({ viewport:{width:w,height:h}, colorScheme: scheme });
  const page = await ctx.newPage();
  const logs=[];
  page.on("console", m=>{ if(["error","warning"].includes(m.type())) logs.push(m.type()+": "+m.text().slice(0,200)); });
  page.on("response", r=>{ if(r.status()>=400) logs.push(r.status()+" "+r.url()); });
  await page.goto(BASE+"/login"); 
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/mật khẩu/i).first().fill(password);
  await page.keyboard.press("Enter");
  await page.waitForURL(u=>!u.pathname.startsWith("/login"),{timeout:15000}).catch(()=>logs.push("login did not leave /login"));
  for (const p of pages) {
    await page.goto(BASE+p, {waitUntil:"networkidle"}).catch(()=>{});
    await page.waitForTimeout(600);
    const slug = p.replace(/[^a-z0-9]+/gi,"_").replace(/^_|_$/g,"")||"root";
    await page.screenshot({ path:`${OUT}/${slug}-${name}-${scheme}.png`, fullPage:true });
    const over = await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
    console.log(name,scheme,p,"->",page.url().replace(BASE,""),over?"HSCROLL":"");
  }
  if(logs.length) console.log(name,scheme,[...new Set(logs)].join("\n  "));
  await ctx.close();
}
await browser.close();
