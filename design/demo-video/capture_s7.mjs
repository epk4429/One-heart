// "이 때" 화면: 서로 다른 선택 → 돌아가기 → 수정 제안 → 다시 계산. 좌표는 public/shots2/s7.json
import fs from "node:fs";
import { launch, mk, toAgree } from "./flow.mjs";

const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);
const { w, act, clickText } = h;

const rectsOf = (text, nth = 0) =>
  page.evaluate(([t, nth]) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const hits = [];
    let n;
    while ((n = walker.nextNode())) if (n.parentElement.offsetParent && n.textContent.includes(t)) hits.push(n);
    const node = hits[nth];
    if (!node) return null;
    const i = node.textContent.indexOf(t);
    const r = document.createRange();
    r.setStart(node, i);
    r.setEnd(node, i + t.length);
    return [...r.getClientRects()].map((q) => ({ x: Math.round(q.x), y: Math.round(q.y), w: Math.round(q.width), h: Math.round(q.height) }));
  }, [text, nth]);
const scrollToText = async (text, top, nth = 0) => {
  await page.evaluate(([t, top, nth]) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const hits = [];
    let n;
    while ((n = walker.nextNode())) if (n.parentElement.offsetParent && n.textContent.includes(t)) hits.push(n);
    const r = document.createRange();
    r.selectNodeContents(hits[nth]);
    window.scrollTo(0, window.scrollY + r.getBoundingClientRect().top - top);
  }, [text, top, nth]);
  await w(1800);
};
const boxOfAct = (a, nth = 0) =>
  page.evaluate(([a, nth]) => {
    const el = [...document.querySelectorAll(`[data-act="${a}"]`)].filter((e) => e.offsetParent)[nth];
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }, [a, nth]);

const meta = {};
await toAgree(page, h, {});

// 민준 A, 서연 C
await act("okpick", 0);
await w(500);
await act("sub");
await w(1800);
await act("viewer");
await w(1000);
await act("okpick", 2);
await w(500);
await act("sub");
await w(4500);
await scrollToText("모두가 고른 방법이 없어요", 330);
await page.screenshot({ path: `${OUT}/a07-diverge.png` });
meta.diverge = { none: await rectsOf("모두가 고른 방법이 없어요"), back: await boxOfAct("back-goal") };
console.log("diverge", JSON.stringify(meta.diverge));

await act("back-goal");
await w(4500);
await scrollToText("제안 2/2", 190, 0);
await page.screenshot({ path: `${OUT}/a07-back.png` });
meta.back = { page: await rectsOf("제안 2/2"), again: await rectsOf("의견을 모아 다시 제안해요"), prev: await boxOfAct("pg-view") };
console.log("again", JSON.stringify(meta.back.again));
console.log("back", JSON.stringify(meta.back));
// 화면에 보이는 머리말 글자 확인용
console.log("heads", JSON.stringify(await page.evaluate(() => [...document.querySelectorAll("h1,h2,h3,.q,.lbl")].filter((e) => e.offsetParent).slice(0, 12).map((e) => e.textContent.trim().slice(0, 40)))));

// 의견 → 숫자 → 동의 → 다시 계산
for (let p = 0; p < 2; p++) {
  await clickText("reply-pick", "좋아요");
  await w(500);
  await act("reply-send");
  await w(3000);
  if (p === 0) {
    await act("viewer");
    await w(1000);
  }
}
await act("approve");
await w(800);
await act("viewer");
await w(800);
await act("approve");
await w(1500);
await act("next");
await w(7000);
await scrollToText("AI가 설계한 방법", 100);
await page.screenshot({ path: `${OUT}/a07-recalc.png` });
meta.recalc = {
  rows: [await boxOfAct("pick", 0), await boxOfAct("pick", 1), await boxOfAct("pick", 2)],
  years: [await rectsOf("약 3.", 0), await rectsOf("약 4.", 0), await rectsOf("약 5.", 0)],
};
console.log("recalc", JSON.stringify(meta.recalc));

fs.writeFileSync(`${OUT}/s7.json`, JSON.stringify(meta, null, 1));
await browser.close();
