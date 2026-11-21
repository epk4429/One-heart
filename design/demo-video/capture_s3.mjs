// 셋째 장면용 화면: 서연·민준의 1:1 대화창, 확인한 요약, 가족 모두의 의견 패널. 좌표는 public/shots2/s3.json
import fs from "node:fs";
import { launch, mk, BASE } from "./flow.mjs";

const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);
const { w, act, has, hideDock } = h;

await page.goto(BASE, { waitUntil: "networkidle" });
await hideDock();
await page.evaluate(() => [...document.querySelectorAll("button")].find((e) => e.textContent.includes("이 예시로 체험하기")).click());
await w(1500);
await hideDock();
await act("setup-done");
await w(800);
await act("next");
await w(1200);
await act("understand");
await w(4000);
await act("next");
await w(1800);

const find = (s) =>
  page.evaluate((s) => {
    const c = [...document.querySelectorAll("body *")].filter((e) => e.offsetParent && e.textContent.includes(s.text) && ![...e.children].some((k) => k.textContent.includes(s.text)));
    let el = c[s.nth || 0];
    if (!el) return null;
    for (let i = 0; i < (s.up || 0) && el.parentElement; i++) el = el.parentElement;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }, s);
const scrollTo = async (text, top) => {
  await page.evaluate(([t, top]) => {
    const el = [...document.querySelectorAll("body *")].find((e) => e.offsetParent && e.textContent.includes(t) && ![...e.children].some((k) => k.textContent.includes(t)));
    window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - top);
  }, [text, top]);
  await w(500);
};

const meta = {};
const snap = async (name, boxes = {}) => {
  const b = {};
  for (const [k, s] of Object.entries(boxes)) b[k] = await find(s);
  await page.screenshot({ path: `${OUT}/${name}.png` });
  meta[name] = b;
  console.log(name, JSON.stringify(b));
};
const chatBoxes = () => ({ head: { text: "1:1 대화", up: 2 }, panel: { text: "가족 모두의 의견", up: 2 } });

async function person(tag) {
  let sends = 0;
  for (let i = 0; i < 14; i++) {
    if (await has("finish")) break;
    const v = await page.evaluate(() => document.querySelector("#ans")?.value);
    await act(v ? "send-ans" : "fill-ans");
    await w(2300);
    if (v) sends++;
    if (v && sends === 2) {
      await scrollTo("1:1 대화", 110);
      await snap(`a03x-chat-${tag}`, chatBoxes());
      await page.evaluate(() => window.scrollTo(0, 0));
    }
  }
  await act("finish");
  await w(3500);
  await scrollTo("1:1 대화", 110);
  await snap(`a03x-sum-${tag}`, chatBoxes());
  await page.evaluate(() => {
    const els = [...document.querySelectorAll('[data-act="confirm"]')];
    els[0]?.scrollIntoView({ block: "center" });
  });
  await w(500);
  await snap(`a03x-sumbtn-${tag}`, { btn: { text: "요약 확인하고 가족에게 공유하기" } });
  await act("confirm");
  await w(1500);
}

await person("seoyeon");
await act("viewer");
await w(1200);
await person("minjun");
await scrollTo("가족 모두의 의견", 110);
await snap("a03x-panel", { panel: { text: "가족 모두의 의견", up: 2 } });

// 서연 요약이 위쪽에 오도록 스크롤
await page.evaluate(() => {
  const el = [...document.querySelectorAll("body *")].find((e) => e.offsetParent && e.children.length === 0 && e.textContent.trim() === "서연" && e.getBoundingClientRect().x > 900);
  window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - 120);
});
await w(500);
await snap("a03x-panel-seoyeon", { panel: { text: "가족 모두의 의견", up: 2 } });

fs.writeFileSync(`${OUT}/s3.json`, JSON.stringify(meta, null, 1));
await browser.close();
