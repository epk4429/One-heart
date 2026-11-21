// 넷째 ② 화면: 미래 계산(방법 A·B·C 표) + 그래프. 좌표는 public/shots2/s5.json
import fs from "node:fs";
import { launch, mk, toAgree } from "./flow.mjs";

const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);

const textRects = (text, nth = 0) =>
  page.evaluate(([t, nth]) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const hits = [];
    let n;
    while ((n = walker.nextNode())) {
      const p = n.parentElement;
      if (p && p.offsetParent && n.textContent.includes(t)) hits.push(n);
    }
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
  await h.w(500);
};
const rowBox = (nth) =>
  page.evaluate((nth) => {
    const el = [...document.querySelectorAll('[data-act="pick"]')].filter((e) => e.offsetParent)[nth];
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }, nth);

const meta = {};
await toAgree(page, h, {
  calc: async () => {
    await scrollToText("AI가 설계한 방법", 100);
    await page.screenshot({ path: `${OUT}/a05y-calc.png` });
    meta.rows = [await rowBox(0), await rowBox(1), await rowBox(2)];
    meta.names = [await textRects("목표 먼저"), await textRects("함께 챙기기"), await textRects("지금 여유 먼저")];
    meta.years = [await textRects("약 3.4년"), await textRects("약 4.0년"), await textRects("약 4.9년")];
    meta.head = await textRects("목표 달성까지");
    console.log("rows", JSON.stringify(meta.rows));
    console.log("names", JSON.stringify(meta.names));
    console.log("years", JSON.stringify(meta.years));
    console.log("head", JSON.stringify(meta.head));
    // 방법 A·B·C를 차례로 눌러 각각의 그래프 화면을 찍는다
    for (const [i, tag] of [[0, "A"], [1, "B"], [2, "C"]]) {
      await page.evaluate((i) => window.scrollTo(0, 0), i);
      await page.evaluate((i) => [...document.querySelectorAll('[data-act="pick"]')].filter((e) => e.offsetParent)[i].click(), i);
      await h.w(1800);
      await scrollToText("를 고르면", 100);
      await page.screenshot({ path: `${OUT}/a05y-chart-${tag}.png` });
      const t = await textRects(`${tag}.`, 0);
      console.log("chart", tag, "ok");
    }
    await page.screenshot({ path: `${OUT}/a05y-chart.png` });
    fs.writeFileSync(`${OUT}/s5.json`, JSON.stringify(meta, null, 1));
    await page.evaluate(() => window.scrollTo(0, 0));
  },
});
await browser.close();
