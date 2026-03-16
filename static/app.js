/* ============================================================
   EarthOne v5 — Final 10/10
   ============================================================ */

(function () {
  "use strict";

  const $ = (s) => document.querySelector(s);

  const elxValueEl   = $("#elx-value");
  const elxDeltaEl   = $("#elx-delta");
  const regimeLabel  = $("#regime-label");
  const biasBadge    = $("#bias-badge");
  const interpEl     = $("#interpretation");
  const assetBiasRow = $("#asset-bias-row");
  const chartWrap    = $("#chart");
  const corrStrip    = $("#corr-strip");
  const driversGrid  = $("#drivers-grid");
  const marketsGrid  = $("#markets-grid");
  const dateEl       = $("#date-now");

  // ---- Date ---------------------------------------------------------------
  function setDate() {
    const d = new Date();
    dateEl.textContent = d.toLocaleDateString("en-US", {
      weekday: "short", year: "numeric", month: "short", day: "numeric",
    }) + "  \u00B7  " + d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  }

  // ---- Animated counter ---------------------------------------------------
  function animateValue(el, target) {
    const dur = 1800;
    const start = performance.now();
    function tick(now) {
      const t = Math.min((now - start) / dur, 1);
      const ease = 1 - Math.pow(1 - t, 4);
      const v = Math.round(target * ease);
      el.innerHTML = `<span class="elx-sign">${target >= 0 ? "+" : ""}</span>${v}`;
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ---- Fetch ELX ----------------------------------------------------------
  async function fetchELX() {
    try {
      const res = await fetch("/api/elx");
      const d = await res.json();

      animateValue(elxValueEl, d.value);

      const deltaSign = d.delta > 0 ? "+" : "";
      const deltaClass = d.delta > 0 ? "delta-up" : d.delta < 0 ? "delta-down" : "delta-flat";
      elxDeltaEl.textContent = `${deltaSign}${d.delta} today`;
      elxDeltaEl.className = "elx-delta " + deltaClass;

      regimeLabel.textContent = d.regime;

      biasBadge.textContent = d.bias;
      biasBadge.className = "bias-badge";
      if (d.bias === "Risk-On") biasBadge.classList.add("bias-green");
      else if (d.bias === "Risk-Off") biasBadge.classList.add("bias-red");
      else biasBadge.classList.add("bias-orange");

      interpEl.textContent = d.interpretation;

      renderAssetBias(d.asset_bias);
      renderDrivers(d.drivers);

      document.body.classList.remove("loading");
    } catch (e) { console.error(e); }
  }

  // ---- Asset bias chips ---------------------------------------------------
  function renderAssetBias(biases) {
    assetBiasRow.innerHTML = "";
    biases.forEach((b) => {
      const arrow = b.direction === "up" ? "\u2191" : b.direction === "down" ? "\u2193" : "\u2192";
      const cls = b.direction === "up" ? "up" : b.direction === "down" ? "down" : "flat";
      const chip = document.createElement("span");
      chip.className = "ab-chip";
      chip.innerHTML = `${b.asset} <span class="ab-arrow ${cls}">${arrow}</span> <span style="color:var(--text-3)">${b.label}</span>`;
      assetBiasRow.appendChild(chip);
    });
  }

  // ---- Drivers ------------------------------------------------------------
  function renderDrivers(drivers) {
    driversGrid.innerHTML = "";
    drivers.forEach((dr) => {
      const ac = dr.direction === "up" ? "arrow-up" : dr.direction === "down" ? "arrow-down" : "arrow-flat";
      const ar = dr.direction === "up" ? "\u2191" : dr.direction === "down" ? "\u2193" : "\u2192";
      const card = document.createElement("div");
      card.className = "driver-card";
      card.innerHTML = `
        <div class="driver-name">${dr.name}</div>
        <div class="driver-score">${dr.score.toFixed(1)}</div>
        <div class="driver-signal"><span class="arrow ${ac}">${ar}</span> ${dr.signal}</div>
        <div class="driver-weight">${dr.weight}% weight</div>
        <div class="weight-track"><div class="weight-fill" style="width:${dr.weight * 2.5}%"></div></div>
      `;
      driversGrid.appendChild(card);
    });
  }

  // ---- Fetch history ------------------------------------------------------
  async function fetchHistory() {
    try {
      const res = await fetch("/api/elx/history?days=365");
      const data = await res.json();
      drawChart(data.series);
    } catch (e) { console.error(e); }
  }

  // ---- 3-period moving average smoothing ----------------------------------
  function smoothMA(values, window) {
    const half = Math.floor(window / 2);
    return values.map((_, i) => {
      let sum = 0, count = 0;
      for (let j = i - half; j <= i + half; j++) {
        if (j >= 0 && j < values.length) { sum += values[j]; count++; }
      }
      return sum / count;
    });
  }

  // ---- Premium SVG Chart --------------------------------------------------
  function drawChart(series) {
    if (!series || series.length < 2) return;

    const W = 980, H = 420;
    const P = { t: 28, r: 16, b: 40, l: 44 };
    const pW = W - P.l - P.r;
    const pH = H - P.t - P.b;

    const rawVals = series.map((p) => p.value);
    const smoothed = smoothMA(rawVals, 5);

    const minV = Math.max(0, Math.min(...smoothed) - 6);
    const maxV = Math.min(100, Math.max(...smoothed) + 6);
    const rV = maxV - minV || 1;

    const pts = smoothed.map((v, i) => ({
      x: P.l + (i / (series.length - 1)) * pW,
      y: P.t + pH - ((v - minV) / rV) * pH,
      v: v,
    }));

    function catmullRom(points) {
      let d = `M${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`;
      for (let i = 0; i < points.length - 1; i++) {
        const p0 = points[Math.max(i - 1, 0)];
        const p1 = points[i];
        const p2 = points[i + 1];
        const p3 = points[Math.min(i + 2, points.length - 1)];
        const t = 0.20;
        d += ` C${(p1.x + (p2.x - p0.x) * t).toFixed(2)},${(p1.y + (p2.y - p0.y) * t).toFixed(2)} ${(p2.x - (p3.x - p1.x) * t).toFixed(2)},${(p2.y - (p3.y - p1.y) * t).toFixed(2)} ${p2.x.toFixed(2)},${p2.y.toFixed(2)}`;
      }
      return d;
    }

    const sampled = [];
    for (let i = 0; i < pts.length; i += 3) sampled.push(pts[i]);
    if (sampled[sampled.length - 1] !== pts[pts.length - 1]) sampled.push(pts[pts.length - 1]);

    const linePath = catmullRom(sampled);
    const areaPath = linePath
      + ` L${sampled[sampled.length - 1].x.toFixed(2)},${(P.t + pH).toFixed(2)}`
      + ` L${sampled[0].x.toFixed(2)},${(P.t + pH).toFixed(2)} Z`;

    const last = pts[pts.length - 1];
    const accent = last.v >= 55 ? "#30d158" : last.v >= 40 ? "#ff9f0a" : "#ff453a";
    const rgb = last.v >= 55 ? "48,209,88" : last.v >= 40 ? "255,159,10" : "255,69,58";

    // Grid
    const steps = 5;
    let grid = "", yL = "";
    for (let i = 0; i <= steps; i++) {
      const v = minV + (rV / steps) * i;
      const y = P.t + pH - (i / steps) * pH;
      grid += `<line x1="${P.l}" y1="${y.toFixed(1)}" x2="${W - P.r}" y2="${y.toFixed(1)}" stroke="rgba(0,0,0,.03)" stroke-width=".6"/>`;
      yL += `<text x="${P.l - 10}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" fill="#c7c7cc" font-size="10" font-weight="500" font-family="Inter,-apple-system,sans-serif">${Math.round(v)}</text>`;
    }

    // X labels
    let xL = "";
    const lc = 7, st = Math.floor(series.length / lc);
    for (let i = 0; i < series.length; i += st) {
      const p = pts[i];
      const label = new Date(series[i].date + "T00:00:00").toLocaleDateString("en-US", { month: "short", year: "2-digit" });
      xL += `<text x="${p.x.toFixed(1)}" y="${(H - 12).toFixed(1)}" text-anchor="middle" fill="#c7c7cc" font-size="10" font-weight="500" font-family="Inter,-apple-system,sans-serif">${label}</text>`;
    }

    const svg = `
    <svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="aG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"  stop-color="rgba(${rgb},.30)"/>
          <stop offset="30%" stop-color="rgba(${rgb},.12)"/>
          <stop offset="100%" stop-color="rgba(${rgb},0)"/>
        </linearGradient>
        <filter id="lGlow" x="-8%" y="-8%" width="116%" height="116%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="b"/>
          <feColorMatrix in="b" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 .5 0"/>
          <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="pGlow" x="-200%" y="-200%" width="500%" height="500%">
          <feGaussianBlur stdDeviation="12" result="b"/>
          <feColorMatrix in="b" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 .7 0"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <radialGradient id="haloG" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="${accent}" stop-opacity=".35"/>
          <stop offset="60%" stop-color="${accent}" stop-opacity=".08"/>
          <stop offset="100%" stop-color="${accent}" stop-opacity="0"/>
        </radialGradient>
        <clipPath id="pClip"><rect x="${P.l}" y="${P.t}" width="${pW}" height="${pH}"/></clipPath>
      </defs>

      ${grid}${yL}${xL}

      <path class="chart-area" d="${areaPath}" fill="url(#aG)" clip-path="url(#pClip)"/>

      <path class="chart-line" d="${linePath}" fill="none"
        stroke="${accent}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
        filter="url(#lGlow)"
        style="stroke-dasharray:5000;stroke-dashoffset:5000"/>

      <g class="chart-pulse">
        <circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="32" fill="url(#haloG)"/>
        <circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="5"
          fill="none" stroke="${accent}" stroke-width="1" opacity=".3">
          <animate attributeName="r" values="6;30" dur="3s" repeatCount="indefinite"/>
          <animate attributeName="opacity" values=".35;0" dur="3s" repeatCount="indefinite"/>
        </circle>
        <circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="5"
          fill="none" stroke="${accent}" stroke-width=".8" opacity=".2">
          <animate attributeName="r" values="6;24" dur="3s" begin="1.5s" repeatCount="indefinite"/>
          <animate attributeName="opacity" values=".25;0" dur="3s" begin="1.5s" repeatCount="indefinite"/>
        </circle>
        <circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="7"
          fill="${accent}" filter="url(#pGlow)" opacity=".85"/>
        <circle cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="2.5"
          fill="#fff"/>
        <line x1="${last.x.toFixed(1)}" y1="${(last.y + 16).toFixed(1)}"
              x2="${last.x.toFixed(1)}" y2="${(P.t + pH).toFixed(1)}"
          stroke="${accent}" stroke-width=".5" stroke-dasharray="2,5" opacity=".12"/>
      </g>
    </svg>`;

    chartWrap.innerHTML = svg;
  }

  // ---- Fetch markets & render correlation strip ---------------------------
  async function fetchMarkets() {
    try {
      const res = await fetch("/api/elx/markets");
      const data = await res.json();
      renderCorrStrip(data);
      renderMarkets(data);
    } catch (e) { console.error(e); }
  }

  // ---- Correlation strip under chart --------------------------------------
  function renderCorrStrip(data) {
    if (!corrStrip) return;
    const tickers = ["SPX", "GOLD", "BTC", "DXY"];
    const labels  = { SPX: "SPX", GOLD: "Gold", BTC: "BTC", DXY: "DXY" };
    let html = "";
    tickers.forEach((t) => {
      const m = data[t];
      if (!m) return;
      const sign = m.correlation > 0 ? "+" : "";
      const cls = m.correlation > 0.15 ? "corr-pos" : m.correlation < -0.15 ? "corr-neg" : "corr-neu";
      html += `<span class="corr-item ${cls}"><span class="corr-label">${labels[t]}</span><span class="corr-val">${sign}${m.correlation.toFixed(2)}</span></span>`;
    });
    corrStrip.innerHTML = `<span class="corr-title">ELX Correlation (90d)</span>` + html;
  }

  // ---- Markets cards ------------------------------------------------------
  function renderMarkets(data) {
    marketsGrid.innerHTML = "";
    ["SPX", "GOLD", "BTC", "DXY"].forEach((ticker) => {
      const m = data[ticker];
      if (!m) return;

      const cc = m.change_30d > 0.5 ? "change-up" : m.change_30d < -0.5 ? "change-down" : "change-flat";
      const cs = m.change_30d > 0 ? "+" : "";
      const corrS = m.correlation > 0 ? "+" : "";

      let priceStr;
      if (m.price >= 10000) priceStr = m.price.toLocaleString("en-US", { maximumFractionDigits: 0 });
      else if (m.price >= 100) priceStr = m.price.toLocaleString("en-US", { maximumFractionDigits: 1 });
      else priceStr = m.price.toFixed(2);

      const card = document.createElement("div");
      card.className = "market-card";
      card.innerHTML = `
        <div class="market-header">
          <span class="market-ticker">${m.label}</span>
          <span class="market-corr">\u03C1 ${corrS}${m.correlation.toFixed(2)}</span>
        </div>
        <div class="market-price">${priceStr}</div>
        <div class="market-change ${cc}">${cs}${m.change_30d}% \u00B7 30d</div>
        <div class="market-spark" id="spark-${ticker}"></div>
      `;
      marketsGrid.appendChild(card);
      drawSparkline(`spark-${ticker}`, m.sparkline, m.change_30d);
    });
  }

  function drawSparkline(id, data, change) {
    const el = document.getElementById(id);
    if (!el || !data || data.length < 2) return;

    const W = 160, H = 36;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const r = max - min || 1;

    const pts = data.map((v, i) => ({
      x: (i / (data.length - 1)) * W,
      y: H - 3 - ((v - min) / r) * (H - 6),
    }));

    let d = `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(i - 1, 0)];
      const p1 = pts[i];
      const p2 = pts[i + 1];
      const p3 = pts[Math.min(i + 2, pts.length - 1)];
      const t = 0.22;
      d += ` C${(p1.x + (p2.x - p0.x) * t).toFixed(1)},${(p1.y + (p2.y - p0.y) * t).toFixed(1)} ${(p2.x - (p3.x - p1.x) * t).toFixed(1)},${(p2.y - (p3.y - p1.y) * t).toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
    }

    const color = change > 0.5 ? "#30d158" : change < -0.5 ? "#ff453a" : "#ff9f0a";
    const rgb = change > 0.5 ? "48,209,88" : change < -0.5 ? "255,69,58" : "255,159,10";
    const area = d + ` L${W},${H} L0,${H} Z`;

    el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <defs><linearGradient id="sg-${id}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="rgba(${rgb},.14)"/>
        <stop offset="100%" stop-color="rgba(${rgb},0)"/>
      </linearGradient></defs>
      <path d="${area}" fill="url(#sg-${id})"/>
      <path d="${d}" fill="none" stroke="${color}" stroke-width="1.2" stroke-linecap="round"/>
    </svg>`;
  }

  // ---- Init ---------------------------------------------------------------
  setDate();
  fetchELX();
  fetchHistory();
  fetchMarkets();
})();
