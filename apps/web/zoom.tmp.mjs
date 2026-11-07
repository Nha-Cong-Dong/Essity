import { chromium } from "@playwright/test";
import fs from "node:fs";
const [email, password] = fs.readFileSync("../../.work/D1-SELFTEST-CORE/account.txt","utf8").trim().split("\n");
const b = await chromium.launch();
for (const sc of ["light","dark"]) {
  const c = await b.newContext({ colorScheme: sc, deviceScaleFactor: 8, viewport:{width:1440,height:900}});
  const p = await c.newPage();
  await p.goto("http://localhost:3100/login");
  await p.getByLabel(/email/i).fill(email); await p.getByLabel(/mật khẩu/i).first().fill(password); await p.keyboard.press("Enter");
  await p.waitForURL(u=>!u.pathname.startsWith("/login"));
  await p.waitForTimeout(1000);
  await p.screenshot({path:`../../.work/D1-SELFTEST-CORE/ev/zoom-logo-${sc}.png`, clip:{x:20,y:25,width:130,height:40}});
  await c.close();
}
await b.close();
