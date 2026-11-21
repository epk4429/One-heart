// "이후" 화면: 가족 홈(이번 달 약속·돈의 흐름) / 재점검 결과 / Ver.2 합의안 / Ver.2 가족 홈. 좌표는 public/shots2/s9.json
import fs from "node:fs";
import { launch, mk, toAgree } from "./flow.mjs";

const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);
const { w, act, setViewer } = h;
const meta = {};

const pickAndSign = async () => {
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
  const signNow = () => page.evaluate(() => document.querySelector(".sig:not(.on):not([disabled])")?.click());
  await signNow();
  await w(1500);
  const other = await page.evaluate(() => {
    const sel = document.querySelector("#viewer");
    return [...sel.options].map((o) => o.value).find((v) => v !== sel.value);
  });
  await setViewer(other);
  await w(1200);
  await signNow();
  await w(2000);
};
const hideFixed = () =>
  page.evaluate(() => {
    for (const e of document.querySelectorAll("body *")) {
      const p = getComputedStyle(e).position;
      if (p === "fixed" || p === "sticky") e.style.visibility = "hidden";
    }
  });
const rectOfText = (text, nth = 0) =>
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
    const all = [...r.getClientRects()];
    const x0 = Math.min(...all.map((q) => q.x)), x1 = Math.max(...all.map((q) => q.x + q.width));
    const y0 = Math.min(...all.map((q) => q.y)), y1 = Math.max(...all.map((q) => q.y + q.height));
    return { x: Math.round(x0), y: Math.round(y0 + window.scrollY), w: Math.round(x1 - x0), h: Math.round(y1 - y0) };
  }, [text, nth]);
const homeShot = async (name) => {
  await hideFixed();
  await page.evaluate(() => window.scrollTo(0, 0));
  await w(800);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true, clip: { x: 0, y: 0, width: 1440, height: 1100 } });
};

await toAgree(page, h, {});
await pickAndSign();
await act("next");
await w(5500);
await act("next");
await w(6000);

// 1) 가족 홈(Ver.1): 이번 달 약속
await homeShot("a09-home");
meta.promise = { head: await rectOfText("이번 달 약속"), l1: await rectOfText("매달 모으기로 한 돈을"), l2: await rectOfText("정한 돈이 예정대로"), l3: await rectOfText("수입·지출이 크게 바뀌었으면") };
console.log("promise", JSON.stringify(meta.promise));
// 스크롤용: 가족 홈 본문(가로 300~1380)을 위에서 '돈의 흐름' 아래까지 긴 한 장으로
await hideFixed();
await page.evaluate(() => window.scrollTo(0, 0));
await w(600);
const tallH = 1560;
await page.screenshot({ path: `${OUT}/a09-tall.png`, fullPage: true, clip: { x: 300, y: 0, width: 1080, height: tallH } });
meta.tall = { w: 1080, h: tallH, head: await rectOfText("지난 3개월 돈의 흐름") };
console.log("tall", JSON.stringify(meta.tall));

// 2) 돈의 흐름 펼침
// (돈의 흐름은 처음부터 펼쳐져 있으므로 누르지 않는다)
await hideFixed();
await page.evaluate(() => {
  const el = [...document.querySelectorAll('[data-act="fold"]')].find((e) => e.textContent.includes("지난 3개월 돈의 흐름"));
  window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - 150);
});
await w(1500);
await page.screenshot({ path: `${OUT}/a09-flow.png` });
meta.flow = await page.evaluate(() => {
  const el = [...document.querySelectorAll('[data-act="fold"]')].find((e) => e.textContent.includes("지난 3개월 돈의 흐름"));
  const r = el.getBoundingClientRect();
  const nx = el.nextElementSibling?.getBoundingClientRect();
  return { head: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }, body: nx ? { x: Math.round(nx.x), y: Math.round(nx.y), w: Math.round(nx.width), h: Math.round(nx.height) } : null };
});
console.log("flow", JSON.stringify(meta.flow));

// 3) 재점검 결과
await page.evaluate(() => [...document.querySelectorAll('[data-act="fold"]')].find((e) => e.textContent.includes("재점검"))?.click());
await w(800);
await page.evaluate(() => {
  const i = document.querySelector('[data-rv="income_delta"]');
  i.value = "-50";
  i.dispatchEvent(new Event("input", { bubbles: true }));
  i.dispatchEvent(new Event("change", { bubbles: true }));
});
await w(500);
await act("review");
await w(2500);
await page.evaluate(() => {
  const el = document.querySelector('[data-act="renegotiate"]');
  window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - 330);
});
await w(1800);
await hideFixed();
await page.screenshot({ path: `${OUT}/a09-review.png` });
meta.review = { result: await page.evaluate(() => { const el = [...document.querySelectorAll(".aibox")].find((e) => e.offsetParent && e.textContent.includes("→")); if (!el) return null; const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; }),
  btn: await page.evaluate(() => { const r = document.querySelector('[data-act="renegotiate"]').getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; }) };
console.log("review", JSON.stringify(meta.review));

// 4) 다시 정하기 → Ver.2 합의안 → 서명 → 가족 홈 Ver.2
await act("renegotiate");
await w(1000);
await page.evaluate(() => [...document.querySelectorAll("button")].find((e) => e.textContent.trim() === "다시 정하기")?.click());
await w(9000);
await act("next");
await w(5000);
await pickAndSign();
await page.evaluate(() => {
  const el = document.querySelector(".sigs");
  window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - 230);
});
await w(1800);
await hideFixed();
await page.screenshot({ path: `${OUT}/a09-agree-v2.png` });
meta.agree = { sealed: await page.evaluate(() => { const r = document.querySelector(".sealed")?.getBoundingClientRect(); return r ? { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) } : null; }), ver: await rectOfText("Ver.2") };
console.log("agree", JSON.stringify(meta.agree));
await act("next");
await w(5500);
await act("next");
await w(6000);
await homeShot("a09-home-v2");
meta.homev2 = { goal: await rectOfText("합의 후") };

fs.writeFileSync(`${OUT}/s9.json`, JSON.stringify(meta, null, 1));
await browser.close();
