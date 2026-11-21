// 합의 후 장면: 서명(민준 → 서연, 확정) / 상품 목록 위쪽 4장 / 가족 홈. 좌표는 public/shots2/s8.json
import fs from "node:fs";
import { launch, mk, toAgree } from "./flow.mjs";

const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);
const { w, act, setViewer } = h;
const meta = {};

await toAgree(page, h, {});
for (let i = 0; i < 2; i++) {
  await act("okpick", 1);
  await w(500);
  await act("sub");
  await w(1800);
  if (i === 0) {
    const cur = await page.evaluate(() => document.querySelector("#viewer").value);
    await act("viewer").catch(() => {});
    await w(1000);
    if ((await page.evaluate(() => document.querySelector("#viewer").value)) === cur) await setViewer("m1");
    await w(800);
  }
}
await w(4500);

const hideFixed = () =>
  page.evaluate(() => {
    for (const e of document.querySelectorAll("body *")) {
      const p = getComputedStyle(e).position;
      if (p === "fixed" || p === "sticky") e.style.visibility = "hidden";
    }
  });
const rectOf = (sel) =>
  page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }, sel);
const scrollEl = async (sel, top) => {
  await page.evaluate(([s, top]) => {
    const el = document.querySelector(s);
    window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - top);
  }, [sel, top]);
  await w(1800);
};

// 1) 서명: 민준 서명 → 서연 서명
await scrollEl(".sigs", 230);
const signNow = () => page.evaluate(() => document.querySelector(".sig:not(.on):not([disabled])")?.click());
await signNow();
await w(1500);
await scrollEl(".sigs", 230);
await page.screenshot({ path: `${OUT}/a08-sign1.png` });
meta.sig1 = { sigs: await rectOf(".sigs"), sigEls: await page.evaluate(() => [...document.querySelectorAll(".sig")].map((e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; })) };
const other = await page.evaluate(() => {
  const sel = document.querySelector("#viewer");
  return [...sel.options].map((o) => o.value).find((v) => v !== sel.value);
});
await setViewer(other);
await w(1200);
await signNow();
await w(2000);
await scrollEl(".sigs", 230);
await page.screenshot({ path: `${OUT}/a08-sign2.png` });
meta.sig2 = { sigs: await rectOf(".sigs"), sealed: await rectOf(".sealed") };
console.log("sign", JSON.stringify(meta));

// 2) 상품 목록
await act("next");
await w(5500);
await hideFixed();
// 영상용: 상태 글씨(확인이 필요해요·지금은 해당하지 않아요 등)의 주황·빨강을 차분한 회색으로(글자 내용은 그대로)
await page.evaluate(() => {
  const keys = ["확인이 필요해요", "지금은 해당하지 않아요", "기본 조건은 맞아요", "해당돼요"];
  for (const e of document.querySelectorAll("body *")) {
    if (e.children.length === 0 && keys.some((k) => e.textContent.includes(k))) e.style.color = "#4D5953";
  }
});
await page.evaluate(() => window.scrollTo(0, 0));
await w(600);
const prod = await page.evaluate(() => {
  const folds = [...document.querySelectorAll('[data-act="fold"]')].filter((e) => e.offsetParent);
  const cards = folds.filter((f) => !f.textContent.includes("왜 이 상품")).slice(0, 4).map((f) => {
    let c = f;
    while (c.parentElement && c.getBoundingClientRect().height < 60) c = c.parentElement;
    const r = c.getBoundingClientRect();
    return { x: r.x, y: r.y + window.scrollY, w: r.width, h: r.height, name: f.textContent.trim().slice(0, 20) };
  });
  const h1 = [...document.querySelectorAll("h1")].find((e) => e.offsetParent);
  const t = h1.getBoundingClientRect();
  return { cards, h1: { x: t.x, y: t.y + window.scrollY, w: t.width, h: t.height } };
});
console.log("prod", JSON.stringify(prod));
const top = Math.max(0, prod.h1.y - 56);
const last = prod.cards[3];
const clip = { x: 431, y: top, width: 826, height: last.y + last.h + 16 - top };
await page.screenshot({ path: `${OUT}/a08-products.png`, fullPage: true, clip });
meta.products = { clipH: clip.height, clipW: clip.width, cards: prod.cards.map((c) => ({ x: c.x - 431, y: c.y - top, w: c.w, h: c.h, name: c.name })) };

// 3) 가족 홈
await act("next");
await w(6000);
await hideFixed();
await page.evaluate(() => window.scrollTo(0, 0));
await w(800);
await page.screenshot({ path: `${OUT}/a08-home.png`, fullPage: true, clip: { x: 0, y: 0, width: 1440, height: 1100 } });
meta.home = {
  texts: await page.evaluate(() => [...document.querySelectorAll("h1,h2,.ct")].filter((e) => e.offsetParent).slice(0, 8).map((e) => { const r = e.getBoundingClientRect(); return { t: e.textContent.trim().slice(0, 24), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; })),
};
console.log("home", JSON.stringify(meta.home));

fs.writeFileSync(`${OUT}/s8.json`, JSON.stringify(meta, null, 1));
await browser.close();
