// 녹화본 체험판의 API(tools/build_demo.py가 web/demo.html에 넣는다). 서버도 AI 호출도 없다.
// - AI 단계: 예시 가족을 실제 Claude로 진행하며 녹화한 응답을 돌려준다(data/demo/rec/*.jsonl).
// - 계산·검사(엔진, 목표 확인, 슬라이더, 재점검): 서버 코드(server/app.py dispatch)를 브라우저 안의 Python(Pyodide)으로 그대로 돌린다.
const ACCESS = { get() { return ""; }, set() { } };
const DEMO_DATA = JSON.parse(document.getElementById("demo-rec").textContent);
window.ONEHEART.DEMO_STANCES = DEMO_DATA.stances;
const AI_PATHS = new Set(["/api/story/understand", "/api/interview/review", "/api/interview/resolve", "/api/goal/analyze",
  "/api/goal/criterion", "/api/options/design", "/api/agreement/check", "/api/agreement/revise", "/api/agreement/draft", "/api/recommend"]);
const PY_BOOT = `
import os, sys, json
os.environ.update({"ALLOW_CUSTOM_FAMILY": "0", "RATE_PER_MIN": "1000000", "LLM_PROVIDER": "replay", "ACCESS_CODES": ""})
sys.path.insert(0, "/app")
from server.app import dispatch
def call(method, path, body):
    st, pl = dispatch(method, path, body.encode("utf-8"), {}, "demo")
    return json.dumps({"status": st, "payload": pl}, ensure_ascii=False)
call
`;

// tools/build_demo.py의 rec_key와 같은 규칙이어야 한다.
function recKey(path, body) {
  const pid = (body.family && body.family.preset_id) || "";
  if (path === "/api/interview/review") return `${pid}|${path}|${body.member_id}|${body.clarification ? 2 : 1}`;
  if (path === "/api/interview/resolve") return `${pid}|${path}|${body.member_id}`;
  if (path === "/api/preset") return `${body.preset_id}|${path}`;
  return `${pid}|${path}`;
}
const clone = o => JSON.parse(JSON.stringify(o));

let PY = null;
function python() {
  if (!PY) PY = (async () => {
    if (typeof loadPyodide !== "function") throw new Error("pyodide 없음");
    const py = await loadPyodide();
    const src = JSON.parse(document.getElementById("demo-py").textContent);
    for (const [p, text] of Object.entries(src)) {
      const parts = ("app/" + p).split("/");
      for (let i = 1; i < parts.length; i++) { const d = "/" + parts.slice(0, i).join("/"); try { py.FS.mkdir(d); } catch (e) { } }
      py.FS.writeFile("/app/" + p, text);
    }
    return py.runPython(PY_BOOT);
  })();
  return PY;
}
setTimeout(() => python().catch(() => { }), 0); // 첫 화면을 보는 동안 미리 불러 둔다(약 10MB, 처음 한 번)

async function api(path, body, method = "POST") {
  const b = clone(body || {});
  if (path === "/api/health") return { ok: true, provider: "recorded", model: "", custom_family: false, access_required: false };
  if (path === "/api/access") return { ok: true };
  const key = recKey(path, b);
  if (AI_PATHS.has(path)) {
    const hit = DEMO_DATA.ai[key];
    if (!hit) throw { code: "not_recorded", message: "녹화본에 없는 단계예요. 예시대로 진행해 주세요." };
    return clone(hit);
  }
  if (DEMO_DATA.fixed[key] && (path === "/api/config" || path === "/api/preset")) return clone(DEMO_DATA.fixed[key]);
  let call;
  try { call = await python(); }
  catch (e) {
    const hit = DEMO_DATA.fixed[key];
    if (hit && !b.override) return clone(hit);
    throw { code: "engine_unavailable", message: "계산 엔진을 불러오지 못했어요. 인터넷 연결을 확인하고 새로고침해 주세요." };
  }
  const out = JSON.parse(call(method, path, JSON.stringify(b)));
  if (out.status !== 200 || out.payload.error) throw out.payload.error || { code: "http_" + out.status, message: "요청이 실패했어요" };
  return out.payload;
}
