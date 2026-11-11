// ==UserScript==
// @name         쇼츠재료 자동 저장 (쇼핑 커넥트 상품)
// @namespace    moneyinsight
// @version      1.0
// @description  쇼핑 커넥트 링크로 연 스마트스토어 상품 페이지에서 상품명·가격·설명·사진을 JSON 한 개로 저장한다 (Claude 숏츠 제작용)
// @match        https://smartstore.naver.com/*/products/*
// @match        https://m.smartstore.naver.com/*/products/*
// @match        https://brand.naver.com/*/products/*
// @match        https://m.brand.naver.com/*/products/*
// @grant        GM_xmlhttpRequest
// @connect      pstatic.net
// @run-at       document-idle
// ==/UserScript==
(function () {
  "use strict";
  const pid = (location.pathname.match(/products\/(\d+)/) || [])[1];
  if (!pid) return;
  const isAffiliate = /NaPm=|aff/i.test(location.search);

  const btn = document.createElement("button");
  btn.textContent = "📦 쇼츠재료 저장";
  Object.assign(btn.style, {position: "fixed", right: "16px", bottom: "90px", zIndex: 999999, padding: "12px 16px",
    background: "#03c75a", color: "#fff", border: "none", borderRadius: "24px", fontSize: "15px", fontWeight: "700",
    boxShadow: "0 4px 14px rgba(0,0,0,.3)", cursor: "pointer"});
  document.body.appendChild(btn);
  const say = t => (btn.textContent = t);

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const toDataURL = url => new Promise(res => {
    GM_xmlhttpRequest({method: "GET", url, responseType: "blob", timeout: 20000,
      onload: r => { if (r.status !== 200) return res(null); const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(r.response); },
      onerror: () => res(null), ontimeout: () => res(null)});
  });

  async function collect() {
    say("⏳ 저장 중...");
    await sleep(2500);
    const firstImgs = [...document.images];               // 위쪽 대표 사진이 먼저 오도록 스크롤 전에 순서를 기록
    for (let i = 0; i < 6; i++) { window.scrollBy(0, 1400); await sleep(500); }
    window.scrollTo(0, 0);
    const all = [...firstImgs, ...document.images];
    const seen = new Set(), imgs = [];
    for (const im of all) {
      const src = (im.currentSrc || im.src || "").split("?")[0];
      if (!/(shop|shopping)-phinf\.pstatic\.net/.test(src) || seen.has(src)) continue;
      const w = im.naturalWidth || 0;
      if (w && w < 300) continue;                          // 아이콘·작은 썸네일 제외
      seen.add(src); imgs.push(src);
      if (imgs.length >= 14) break;
    }
    const meta = p => (document.querySelector(`meta[property="${p}"]`) || {}).content || "";
    const images = [];
    for (let i = 0; i < imgs.length; i++) {
      say(`⏳ 사진 ${i + 1}/${imgs.length}`);
      const d = await toDataURL(imgs[i]);
      if (d) images.push({url: imgs[i], data: d});
    }
    const data = {
      saved_at: new Date().toISOString(), product_no: pid, url: location.href.split("?")[0],
      title: meta("og:title") || document.title, description: meta("og:description"), og_image: meta("og:image"),
      text: document.body.innerText.slice(0, 12000), images
    };
    const blob = new Blob([JSON.stringify(data)], {type: "application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `쇼츠재료_${pid}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    say(`✅ 저장 완료 (사진 ${images.length}장)`);
  }
  btn.addEventListener("click", collect);
  if (isAffiliate && !sessionStorage.getItem("shorts_saved_" + pid)) {   // 쇼핑 커넥트 링크로 열었으면 자동 저장
    sessionStorage.setItem("shorts_saved_" + pid, "1");
    setTimeout(collect, 1500);
  }
})();
