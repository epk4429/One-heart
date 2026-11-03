// mock 체험판의 API(tools/build_demo.py가 web/demo.html에 넣는다). 서버도 실제 AI 호출도 없다.
// - 모든 단계: 서버 코드(server/app.py dispatch)를 브라우저 안의 Python(Pyodide)으로 그대로 돌린다.
//   AI 단계는 개발용 재생 공급자(llm/replay.py)가 규칙으로 바로 답한다(mock, 녹화 없음).
// - 첫 화면(설정·예시 가족)은 만들 때 미리 계산해 둔 값으로 바로 보여 준다(Pyodide를 기다리지 않음).
const ACCESS = { get() { return ""; }, set() { } };
const DEMO_DATA = JSON.parse(document.getElementById("demo-data").textContent);
window.ONEHEART.DEMO_STANCES = DEMO_DATA.stances;
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

// tools/build_demo.py의 demo_data 키와 같은 규칙이어야 한다.
const fixedKey = (path, body) => path === "/api/preset" ? `${path}|${body.preset_id}` : path;
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
  if (path === "/api/health") return { ok: true, provider: "mock", model: "", custom_family: false, access_required: false };
  if (path === "/api/access") return { ok: true };
  const hit = DEMO_DATA.fixed[fixedKey(path, b)];
  if (hit) return clone(hit);
  let call;
  try { call = await python(); }
  catch (e) { throw { code: "engine_unavailable", message: "계산 엔진을 불러오지 못했어요. 인터넷 연결을 확인하고 새로고침해 주세요." }; }
  const out = JSON.parse(call(method, path, JSON.stringify(b)));
  if (out.status !== 200 || out.payload.error) throw out.payload.error || { code: "http_" + out.status, message: "요청이 실패했어요" };
  return out.payload;
}
