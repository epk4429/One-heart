// 다섯째 2차: 합의안 문서 전체(위→아래 스크롤용 긴 이미지) + 실행 계획 세 줄 위치. public/shots2/s6b.json
import fs from "node:fs";
import { launch, mk, toAgree } from "./flow.mjs";

const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);
const { w, act } = h;

await toAgree(page, h, {});
// 두 사람 모두 B 선택
for (let i = 0; i < 2; i++) {
  await act("okpick", 1);
  await w(500);
  await act("sub");
  await w(1800);
  if (i === 0) {
    const cur = await page.evaluate(() => document.querySelector("#viewer").value);
    await act("viewer").catch(() => {});
    await w(1000);
    if ((await page.evaluate(() => document.querySelector("#viewer").value)) === cur) await h.setViewer("m1");
    await w(800);
  }
}
await w(5000);

// 합의안 문서(article)를 한 장으로
const info = await page.evaluate(() => {
  const arts = [...document.querySelectorAll("article")].filter((e) => e.offsetParent && e.textContent.includes("실행 계획"));
  const el = arts[0];
  if (!el) return null;
  el.setAttribute("data-cap", "doc");
  el.scrollIntoView({ block: "start" });
  const r = el.getBoundingClientRect();
  const plans = [...el.querySelectorAll("li")].filter((li) => /약속대로|확인해요|다시 정해요|자동이체|모였는지/.test(li.textContent));
  const rect = (n) => {
    const range = document.createRange();
    range.selectNodeContents(n);
    const q = range.getClientRects()[0] || n.getBoundingClientRect();
    const all = [...range.getClientRects()];
    const x0 = Math.min(...all.map((a) => a.x)), x1 = Math.max(...all.map((a) => a.x + a.width));
    const y0 = Math.min(...all.map((a) => a.y)), y1 = Math.max(...all.map((a) => a.y + a.height));
    return { x: x0 - r.x, y: y0 - r.y, w: x1 - x0, h: y1 - y0 };
  };
  const title = [...el.querySelectorAll("b, h4, strong")].find((n) => n.textContent.trim() === "실행 계획");
  return { w: r.width, h: r.height, title: title ? rect(title) : null, plans: plans.map(rect), plansText: plans.map((p) => p.textContent.trim()) };
});
console.log(JSON.stringify(info));
// 위쪽 고정 헤더 등이 문서 위에 겹쳐 찍히지 않게 숨긴다
await page.evaluate(() => {
  for (const e of document.querySelectorAll("body *")) {
    const p = getComputedStyle(e).position;
    if (p === "fixed" || p === "sticky") e.style.visibility = "hidden";
  }
});
await w(400);
await page.locator('[data-cap="doc"]').screenshot({ path: `${OUT}/a06z-doc.png` });
fs.writeFileSync(`${OUT}/s6b.json`, JSON.stringify(info, null, 1));
await browser.close();
