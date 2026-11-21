// 서비스 흐름을 자동으로 누르는 공통 도구 (재생 모드 서버, AI 비용 0원)
import { chromium } from "playwright-core";

export const BASE = process.env.BASE || "http://localhost:8770";

export async function launch() {
  const browser = await chromium.launch({
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    headless: true,
  });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, locale: "ko-KR" });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log("pageerror", e.message));
  return { browser, ctx, page };
}

export const mk = (page, OUT) => {
  const w = (ms) => page.waitForTimeout(ms);
  const act = async (a, nth = 0) => {
    await page.evaluate(([a, nth]) => {
      const el = [...document.querySelectorAll(`[data-act="${a}"]`)].filter((e) => !e.disabled)[nth];
      if (!el) throw new Error("없는 버튼 " + a);
      el.click();
    }, [a, nth]);
  };
  const has = (a) => page.evaluate((a) => !!document.querySelector(`[data-act="${a}"]:not([disabled])`), a);
  const clickText = (a, t) =>
    page.evaluate(([a, t]) => {
      const el = [...document.querySelectorAll(`[data-act="${a}"]`)].find((e) => e.textContent.trim().includes(t));
      if (!el) throw new Error("없는 버튼 " + t);
      el.click();
    }, [a, t]);
  const shot = async (name) => {
    await w(600);
    await page.screenshot({ path: `${OUT}/${name}.png` });
    console.log("shot", name);
  };
  const hideDock = () => page.addStyleTag({ content: ".dock{display:none!important}" });
  const list = () =>
    page.evaluate(() =>
      JSON.stringify({
        h: [...document.querySelectorAll("h1,h2")].filter((e) => e.offsetParent).slice(0, 4).map((e) => e.textContent.trim().slice(0, 40)),
        b: [...document.querySelectorAll("button")].filter((e) => e.offsetParent && !e.disabled && e.dataset.act !== "go").map((e) => (e.dataset.act || "") + "|" + e.textContent.trim().slice(0, 26)),
      })
    );
  const setViewer = (v) =>
    page.evaluate((v) => {
      const sel = document.querySelector("#viewer");
      sel.value = v;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    }, v);
  return { w, act, has, clickText, shot, hideDock, list, setViewer };
};

// 소개 → 예시 가족 → 1~3단계(입력·대화) → 4단계(공동 목표) → 5단계(미래 계산) → 6단계 '각자 괜찮은 방법 고르기' 화면까지
export async function toAgree(page, h, hooks = {}) {
  const { w, act, has, clickText, hideDock } = h;
  await page.goto(BASE, { waitUntil: "networkidle" });
  await hideDock();
  await page.evaluate(() => [...document.querySelectorAll("button")].find((e) => e.textContent.includes("이 예시로 체험하기")).click());
  await w(1500);
  await hideDock();
  await hooks.afterFamilyRoom?.();
  await act("setup-done");
  await w(800);
  await act("next");
  await w(1200);
  await hooks.storyTop?.();
  await act("understand");
  await w(4000);
  await hooks.storyDone?.();
  await act("next");
  await w(1500);
  const interview = async (first) => {
    for (let i = 0; i < 14; i++) {
      if (await has("finish")) break;
      const v = await page.evaluate(() => document.querySelector("#ans")?.value);
      await act(v ? "send-ans" : "fill-ans");
      await w(2300);
      if (i === 3) await hooks.chat?.(first);
    }
    await act("finish");
    await w(3500);
    await hooks.summary?.(first);
    await act("confirm");
    await w(1500);
  };
  await interview(true);
  await act("viewer");
  await w(1200);
  await interview(false);
  await act("next");
  await w(4500);
  await hooks.goalThink?.();
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
  await hooks.goalSize?.();
  await act("approve");
  await w(800);
  await act("viewer");
  await w(800);
  await act("approve");
  await w(1500);
  await act("next");
  await w(7000);
  await hooks.calc?.();
  await act("next");
  await w(5000);
}
