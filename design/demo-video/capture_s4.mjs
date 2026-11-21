// 넷째 ① 화면: 생각 확인(같은 생각/갈리는 생각) + AI의 제안. 좌표는 public/shots2/s4.json
import fs from "node:fs";
import { launch, mk, toAgree } from "./flow.mjs";

const OUT = "public/shots2";
const { browser, page } = await launch();
const h = mk(page, OUT);

const find = (s) =>
  page.evaluate((s) => {
    const c = [...document.querySelectorAll("body *")].filter((e) => e.offsetParent && e.textContent.includes(s.text) && ![...e.children].some((k) => k.textContent.includes(s.text)));
    let el = c[s.nth || 0];
    if (!el) return null;
    for (let i = 0; i < (s.up || 0) && el.parentElement; i++) el = el.parentElement;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  }, s);
const scrollTo = async (text, nth, top) => {
  await page.evaluate(([t, n, top]) => {
    const c = [...document.querySelectorAll("body *")].filter((e) => e.offsetParent && e.textContent.includes(t) && ![...e.children].some((k) => k.textContent.includes(t)));
    const el = c[n];
    window.scrollTo(0, window.scrollY + el.getBoundingClientRect().top - top);
  }, [text, nth, top]);
  await h.w(500);
};

// 글자가 실제로 차지하는 영역(줄마다). 박스가 아니라 글자 폭에 맞춘 강조에 쓴다.
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

const meta = {};
const probe = async (label, text, ups, nth = 0) => {
  const o = {};
  for (const u of ups) o[`up${u}`] = await find({ text, up: u, nth });
  meta[label] = o;
  console.log(label, JSON.stringify(o));
};

await toAgree(page, h, {
  goalThink: async () => {
    // 생각 확인 화면: 제목이 위쪽에 오도록
    await scrollTo("생각 확인", 1, 110);
    await page.screenshot({ path: `${OUT}/a04y-think.png` });
    await probe("same", "이미 같은 생각인 부분", [0, 1, 2, 3]);
    await probe("diff", "생각이 갈리는 부분", [0, 1, 2, 3]);
    await probe("mj", "우리 집에서 아이랑 사는 거요", [0, 1, 2, 3]);
    await probe("sy", "아이가 있고, 제가 육아휴직을", [0, 1, 2, 3]);
    meta.t_same = await textRects("이미 같은 생각인 부분");
    meta.t_diff = await textRects("생각이 갈리는 부분");
    meta.t_mj = await textRects("우리 집에서 아이랑 사는 거요", 0);
    meta.t_sy = await textRects("아이가 있고, 제가 육아휴직을", 0);
    console.log("t_same", JSON.stringify(meta.t_same), "t_diff", JSON.stringify(meta.t_diff));
    console.log("t_mj", JSON.stringify(meta.t_mj), "t_sy", JSON.stringify(meta.t_sy));
    // AI의 제안: 제목이 위쪽에 오도록
    await scrollTo("AI의 제안", 1, 110);
    await page.screenshot({ path: `${OUT}/a04y-propose.png` });
    await probe("pbox", "이렇게 해 보면 어때요", [0, 1, 2, 3]);
    await probe("cover", "모두의 지키고 싶은 것을 담았어요", [0, 1, 2, 3]);
    await probe("reason", "이런 이유로 제안했어요", [0, 1, 2]);
    meta.t_cover = await textRects("모두의 지키고 싶은 것을 담았어요");
    meta.t_cover_mj = await textRects("민준님", 1);
    meta.t_cover_sy = await textRects("서연님", 1);
    for (const k of ["t_cover", "t_cover_mj", "t_cover_sy"]) console.log(k, JSON.stringify(meta[k]));
    fs.writeFileSync(`${OUT}/s4.json`, JSON.stringify(meta, null, 1));
    await page.evaluate(() => window.scrollTo(0, 0));
  },
});
await browser.close();
