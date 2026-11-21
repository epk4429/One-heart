// 둘째 장면용 화면: 금융정보 줄 / 카테고리+목표 금액. 좌표는 public/shots2/s2.json
import fs from "node:fs";
import { launch, mk, BASE } from "./flow.mjs";

const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);
const { w, act, hideDock } = h;

await page.goto(BASE, { waitUntil: "networkidle" });
await hideDock();
await page.evaluate(() => [...document.querySelectorAll("button")].find((e) => e.textContent.includes("이 예시로 체험하기")).click());
await w(1500);
await hideDock();
await act("setup-done");
await w(800);
await act("next");
await w(1500);

const find = (s) =>
  page.evaluate((s) => {
    let el = null;
    if (s.act) el = [...document.querySelectorAll(`[data-act="${s.act}"]`)].filter((e) => e.offsetParent).find((e) => e.textContent.includes(s.text));
    else {
      const c = [...document.querySelectorAll("body *")].filter(
        (e) => e.offsetParent && ((e.textContent.includes(s.text) && ![...e.children].some((k) => k.textContent.includes(s.text))) || (e.tagName === "INPUT" && String(e.value).includes(s.text)))
      );
      el = c[0];
    }
    if (!el) return null;
    for (let i = 0; i < (s.up || 0) && el.parentElement; i++) el = el.parentElement;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }, s);

const scrollTo = async (text, top) => {
  await page.evaluate(
    ([t, top]) => {
      const el = [...document.querySelectorAll("body *")].find(
        (e) => e.offsetParent && ((e.textContent.includes(t) && ![...e.children].some((k) => k.textContent.includes(t))) || (e.tagName === "INPUT" && String(e.value).includes(t)))
      );
      window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - top);
    },
    [text, top]
  );
  await w(500);
};

const meta = {};
const snap = async (name, boxes) => {
  const b = {};
  for (const [k, s] of Object.entries(boxes)) b[k] = await find(s);
  await page.screenshot({ path: `${OUT}/${name}.png` });
  meta[name] = b;
  console.log(name, JSON.stringify(b));
};

// A) 금융정보 줄: 월 수입 줄이 위쪽에 오게
await scrollTo("둘이 버는 돈", 130);
await snap("a02d-fin", {
  income0: { text: "둘이 버는 돈" }, income1: { text: "둘이 버는 돈", up: 1 }, income2: { text: "둘이 버는 돈", up: 2 },
  dep0: { text: "가온은행 예금" }, dep1: { text: "가온은행 예금", up: 1 }, dep2: { text: "가온은행 예금", up: 2 },
  loan0: { text: "가온은행 전세대출" }, loan1: { text: "가온은행 전세대출", up: 1 }, loan2: { text: "가온은행 전세대출", up: 2 },
});

// B) 카테고리 + 목표 금액
await scrollTo("가장 이루고 싶은 목표", 110);
await snap("a02e-cat-goal", {
  cat: { act: "gi-cat", text: "내 집 마련" }, amt0: { text: "30000" }, amt1: { text: "30000", up: 1 }, amt2: { text: "30000", up: 2 },
});

fs.writeFileSync(`${OUT}/s2.json`, JSON.stringify(meta, null, 1));
await browser.close();
