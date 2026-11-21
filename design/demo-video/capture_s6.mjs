// 다섯째 화면: 각자 괜찮은 방법 고르기(카드) / 선택된 상태 / 합의안 문서의 실행 계획. 좌표는 public/shots2/s6.json
import fs from "node:fs";
import { launch, mk, toAgree } from "./flow.mjs";

const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);
const { w, act } = h;

const textRects = (text, nth = 0) =>
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
  await w(1800); // 알림 문구 등이 사라져 화면이 안정될 때까지
};
const boxOfAct = (a, nth) =>
  page.evaluate(([a, nth]) => {
    const el = [...document.querySelectorAll(`[data-act="${a}"]`)].filter((e) => e.offsetParent)[nth];
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }, [a, nth]);

const meta = {};
await toAgree(page, h, {});

// 1) 고르기 화면(아무도 안 고른 상태)
await scrollToText("각자 괜찮은 방법 고르기", 90, 0);
await page.screenshot({ path: `${OUT}/a06y-pick.png` });
meta.cards = [await boxOfAct("okpick", 0), await boxOfAct("okpick", 1), await boxOfAct("okpick", 2)];
meta.sub = await boxOfAct("sub", 0);
meta.years = [await textRects("약 3.4년", 1), await textRects("약 4.0년", 1), await textRects("약 4.9년", 1)]; // 0번은 위쪽 점검표, 1번이 카드
console.log("cards", JSON.stringify(meta.cards));
console.log("years", JSON.stringify(meta.years));
console.log("sub", JSON.stringify(meta.sub));

// 2) 민준이 B 선택한 상태
await act("okpick", 1);
await w(600);
await page.screenshot({ path: `${OUT}/a06y-pick-B.png` });
meta.cardsB = [await boxOfAct("okpick", 0), await boxOfAct("okpick", 1), await boxOfAct("okpick", 2)];

// 3) 두 사람 모두 B 선택 → 합의안 문서
await act("sub");
await w(1800);
const cur = await page.evaluate(() => document.querySelector("#viewer").value);
await act("viewer").catch(() => {});
await w(1000);
if ((await page.evaluate(() => document.querySelector("#viewer").value)) === cur) await h.setViewer("m1");
await w(800);
await act("okpick", 1);
await w(500);
await act("sub");
await w(4500);
await scrollToText("실행 계획", 220, 0);
await page.screenshot({ path: `${OUT}/a06y-doc.png` });
meta.plan = await textRects("실행 계획", 0);
meta.plan1 = await textRects("자동이체를 약속대로 설정해요", 0);
meta.report = await textRects("왜 이 방법인가요", 0);
console.log("plan", JSON.stringify(meta.plan), JSON.stringify(meta.plan1), JSON.stringify(meta.report));

fs.writeFileSync(`${OUT}/s6.json`, JSON.stringify(meta, null, 1));
await browser.close();
