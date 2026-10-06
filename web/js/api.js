// API 호출. 오류는 {code, message}로 던진다. 체험 코드가 있으면 X-Access-Code 헤더로 보낸다.
const ACCESS = {
  get() { try { return localStorage.getItem("oneheart.code") || ""; } catch (e) { return ""; } },
  set(v) { try { v ? localStorage.setItem("oneheart.code", v) : localStorage.removeItem("oneheart.code"); } catch (e) { } },
};
async function api(path, body, method = "POST") {
  const headers = { "Content-Type": "application/json" };
  const code = ACCESS.get();
  if (code) headers["X-Access-Code"] = code;
  const opt = { method, headers };
  if (method === "POST") opt.body = JSON.stringify(body || {});
  let res;
  try {
    res = await fetch(window.ONEHEART.API_BASE + path, opt);
  } catch (e) {
    throw { code: "network", message: "서버에 연결하지 못했어요" };
  }
  let data;
  try { data = await res.json(); } catch (e) { throw { code: "bad_response", message: "응답을 읽지 못했어요" }; }
  if (!res.ok || data.error) {
    const err = data.error || { code: "http_" + res.status, message: "요청이 실패했어요" };
    if (err.code === "access_denied" && window.onAccessDenied) window.onAccessDenied();
    throw err;
  }
  return data;
}
