// 셋째 장면 2차: 채팅창 전체(위→아래 스크롤용 긴 이미지)와 넓게 펼친 '가족 모두의 의견' 패널
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

const meta = {};

// 채팅 카드 전체를 펼쳐서(안쪽 스크롤 제거) 한 장으로 찍는다
async function chatFull(tag) {
  const info = await page.evaluate(() => {
    let el = [...document.querySelectorAll("body *")].find((e) => e.offsetParent && e.children.length === 0 && e.textContent.includes("1:1 대화"));
    while (el && el.getBoundingClientRect().height < 400) el = el.parentElement;
    el.setAttribute("data-cap", "card");
    window.__mods = [];
    for (const e of [el, ...el.querySelectorAll("*")]) {
      const cs = getComputedStyle(e);
      if (e === el || (["auto", "scroll", "hidden"].includes(cs.overflowY) && e.scrollHeight > e.clientHeight + 2)) {
        window.__mods.push([e, e.getAttribute("style")]);
        e.style.maxHeight = "none";
        e.style.height = "auto";
        e.style.overflow = "visible";
      }
    }
    el.scrollIntoView({ block: "start" });
    return null;
  });
  await w(600);
  const box = await page.evaluate(() => {
    const el = document.querySelector('[data-cap="card"]');
    const r = el.getBoundingClientRect();
    const btn = [...el.querySelectorAll('[data-act="confirm"]')][0];
    const br = btn?.getBoundingClientRect();
    return { w: r.width, h: r.height, x: r.x, y: r.y, btn: br ? { x: br.x - r.x, y: br.y - r.y, w: br.width, h: br.height } : null };
  });
  await page.locator('[data-cap="card"]').screenshot({ path: `${OUT}/a03y-chat-${tag}.png` });
  await page.evaluate(() => {
    document.querySelector('[data-cap="card"]').removeAttribute("data-cap");
    for (const [e, s] of window.__mods) (s === null ? e.removeAttribute("style") : e.setAttribute("style", s));
  });
  meta[`chat-${tag}`] = box;
  console.log("chat", tag, JSON.stringify(box));
}

async function person(tag) {
  for (let i = 0; i < 14; i++) {
    if (await has("finish")) break;
    const v = await page.evaluate(() => document.querySelector("#ans")?.value);
    await act(v ? "send-ans" : "fill-ans");
    await w(2300);
  }
  await act("finish");
  await w(3500);
  await chatFull(tag);
  await w(500);
  await act("confirm");
  await w(1500);
}

// 새로고침해도 상태가 남는지 확인하며 진행
await person("seoyeon");
await act("viewer");
await w(1200);
await person("minjun");

// 넓게 펼친 '가족 모두의 의견' 패널
const pbox = await page.evaluate(() => {
  let el = [...document.querySelectorAll("body *")].find((e) => e.offsetParent && e.children.length === 0 && e.textContent.trim() === "가족 모두의 의견");
  while (el && !(el.getBoundingClientRect().width > 240 && el.getBoundingClientRect().height > 300)) el = el.parentElement;
  el.setAttribute("data-cap", "panel");
  for (const e of [...el.querySelectorAll("*")]) {
    if (e.children.length === 0 && e.textContent.trim() === "나") e.style.display = "none";
  }
  el.style.cssText += ";position:fixed;left:30px;top:30px;width:860px;max-width:none;background:#fff;padding:26px 30px;box-sizing:border-box;z-index:9999;";
  const r = el.getBoundingClientRect();
  return { w: r.width, h: r.height };
});
await w(600);
await page.locator('[data-cap="panel"]').screenshot({ path: `${OUT}/a03y-panel.png` });
meta.panel = pbox;
console.log("panel", JSON.stringify(pbox));

fs.writeFileSync(`${OUT}/s3b.json`, JSON.stringify(meta, null, 1));
await browser.close();
