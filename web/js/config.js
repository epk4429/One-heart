// API 서버 주소. 같은 출처(dev_server.py, 또는 Vercel 하나로 화면까지 올린 경우)면 빈 문자열.
// GitHub Pages로 화면을 올리면 아래 VERCEL_API에 Vercel 배포 주소를 넣는다(docs/09_시스템과_배포.md).
(function () {
  const VERCEL_API = ""; // 예: "https://one-heart.vercel.app"
  const onPages = /\.github\.io$/.test(location.hostname);
  window.ONEHEART = { API_BASE: onPages ? VERCEL_API : "" };
})();
