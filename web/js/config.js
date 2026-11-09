// API 서버 주소. 같은 출처(dev_server.py, 또는 Vercel 하나로 화면까지 올린 경우)면 빈 문자열.
// GitHub Pages로 화면을 올리면 아래 VERCEL_API에 Vercel 배포 주소를 넣는다(docs/09_시스템과_배포.md).
(function () {
  const VERCEL_API = ""; // 예: "https://one-heart.vercel.app"
  const onPages = /\.github\.io$/.test(location.hostname);
  // 파일럿에서 화면에만 감추는 것(코드·데이터는 그대로, 2026-11-08 형님 결정, 목록은 임의결정 58 · docs/00_할일.md 1-2).
  // 다시 보이게 하려면 여기서 false로 바꾸거나 줄을 지운다.
  const HIDE = {
    graph_link: true, // 상품 추천 화면의 '온톨로지 연결 그래프 보기' 링크(/graph.html 자체는 설명용으로 남김)
  };
  window.ONEHEART = { API_BASE: onPages ? VERCEL_API : "", HIDE };
})();
