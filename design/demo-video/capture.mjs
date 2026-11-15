// ONE-Heart 데모 영상용 화면 캡처 (재생 모드 서버 http://localhost:8770, AI 비용 0원)
// 사용: node capture.mjs   → public/shots/*.png
import { chromium } from "playwright-core";
import fs from "node:fs";

const BASE = process.env.BASE || "http://localhost:8770";
const OUT = "public/shots";
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({
  executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  headless: true,
});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, locale: "ko-KR" });
const page = await ctx.newPage();
page.on("pageerror", (e) => console.log("pageerror", e.message));

const w = (ms) => page.waitForTimeout(ms);
const shot = async (name) => {
  await w(600);
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log("shot", name);
};
const act = async (a, nth = 0) => {
  await page.evaluate(([a, nth]) => {
    const el = [...document.querySelectorAll(`[data-act="${a}"]`)].filter((e) => !e.disabled)[nth];
    if (!el) throw new Error("없는 버튼 " + a);
    el.click();
  }, [a, nth]);
};
const has = (a) => page.evaluate((a) => !!document.querySelector(`[data-act="${a}"]:not([disabled])`), a);
const clickText = async (act_, text) => {
  await page.evaluate(([a, t]) => {
    const el = [...document.querySelectorAll(`[data-act="${a}"]`)].find((e) => e.textContent.trim() === t);
    if (!el) throw new Error("없는 버튼 " + t);
    el.click();
  }, [act_, text]);
};
const scrollTo = async (sel, block = "start") => {
  await page.evaluate(([s, b]) => document.querySelector(s)?.scrollIntoView({ block: b }), [sel, block]);
};

// 개발용 하단 막대 숨기기(영상에는 나오면 안 됨)
const hideDock = () => page.addStyleTag({ content: ".dock{display:none!important}" });

// 1) 소개 페이지
await page.goto(BASE, { waitUntil: "networkidle" });
await hideDock();
await shot("01-landing");

// 예시 가족으로 시작
await page.evaluate(() => [...document.querySelectorAll("button")].find((e) => e.textContent.includes("이 예시로 체험하기")).click());
await w(1500);
await hideDock();
await shot("02-family-room");
await act("setup-done");
await w(800);
await act("next");
await w(1200);
await shot("03-story-top");
await scrollTo(".fin, #app h2:nth-of-type(3)");
await act("understand");
await w(4000);
await shot("04-story-done");
await act("next");
await w(1500);

// 각자의 생각: 한 사람씩 예시 답 → 요약 → 공유
async function interview(first) {
  for (let i = 0; i < 14; i++) {
    if (await has("finish")) break;
    const v = await page.evaluate(() => document.querySelector("#ans")?.value);
    await act(v ? "send-ans" : "fill-ans");
    await w(i === 1 && first ? 1500 : 2300);
    if (first && i === 3) await shot("05-interview-chat");
  }
  await act("finish");
  await w(3500);
  if (first) await shot("06-interview-summary");
  await act("confirm");
  await w(1500);
}
await interview(true);
await act("viewer");
await w(1200);
await interview(false);
await act("next");
await w(4500);

// 공동 목표: 생각 확인 + AI의 제안
await shot("07-goal-think");
const goalMid = async () => {
  await page.evaluate(() => window.scrollTo(0, 560));
  await w(500);
};
await goalMid();
await shot("08-goal-propose");
await page.evaluate(() => window.scrollTo(0, 0));
for (let p = 0; p < 2; p++) {
  await clickText("reply-pick", "좋아요");
  await w(500);
  if (p === 0) {
    await goalMid();
    await shot("09-goal-reply");
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  await act("reply-send");
  await w(3000);
  if (p === 0) {
    await act("viewer");
    await w(1000);
  }
}
await shot("10-goal-size");
await act("approve");
await w(800);
await act("viewer");
await w(800);
await act("approve");
await w(1500);
await shot("11-goal-agreed");
await act("next");
await w(7000);

// 미래 계산
await shot("12-calc-top");
await page.evaluate(() => window.scrollTo(0, 520));
await shot("13-calc-chart");
await page.evaluate(() => window.scrollTo(0, 0));
await act("next");
await w(5000);

// 합의안: 각자 B 고르기 → 서명
await shot("14-agree-pick");
for (let i = 0; i < 2; i++) {
  await act("okpick", 1);
  await w(500);
  if (i === 0) await shot("15-agree-picked");
  await act("sub");
  await w(1800);
  if (i === 0) {
    await act("viewer");
    await w(1000);
  }
}
await w(3500);
await shot("16-agree-doc");
await page.evaluate(() => window.scrollTo(0, 480));
await shot("17-agree-doc-lower");
await page.evaluate(() => window.scrollTo(0, 0));
const signNow = () => page.evaluate(() => document.querySelector(".sig:not(.on):not([disabled])")?.click());
await signNow();
await w(1500);
// 아직 서명하지 않은 사람 화면으로 바꿔서 서명
const other = await page.evaluate(() => {
  const sel = document.querySelector("#viewer");
  return [...sel.options].map((o) => o.value).find((v) => v !== sel.value);
});
await page.evaluate((v) => {
  const sel = document.querySelector("#viewer");
  sel.value = v;
  sel.dispatchEvent(new Event("change", { bubbles: true }));
}, other);
await w(1200);
await signNow();
await w(2000);
await page.evaluate(() => window.scrollTo(0, 560));
await shot("18-agree-signed");
await page.evaluate(() => window.scrollTo(0, 0));
await act("next");
await w(5000);

// 상품 비교
await shot("19-products");
await act("next");
await w(5000);

// 가족 홈
await shot("20-home");
await page.evaluate(() => window.scrollTo(0, 500));
await shot("21-home-lower");

await browser.close();
console.log("완료");
