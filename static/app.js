/* ============================================================
   EarthOne V4 — Distribution + Regime Intelligence
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
  const rangeBar     = $("#range-bar");
  const shareBtn     = $("#share-btn");
  const regimePointer = $("#regime-pointer");
  const regimeAlert  = $("#regime-alert");

  let currentRange = "1Y";
  let elxHistory90 = null; // cached for overlay charts
  const RANGE_DAYS = { "1Y": 365, "5Y": 1825, "10Y": 3650, "MAX": 7300 };

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
    const isNeg = target < 0;
    const abs = Math.abs(target);
    function tick(now) {
      const t = Math.min((now - start) / dur, 1);
      const ease = 1 - Math.pow(1 - t, 4);
      const v = Math.round(abs * ease);
      const sign = isNeg ? "\u2212" : "+";
      el.innerHTML = `<span class="elx-sign">${sign}</span>${v}`;
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ---- Regime Map Pointer -------------------------------------------------
  function updateRegimeMap(value) {
    if (!regimePointer) return;
    // value ranges from -100 to +100, map to 0%-100% of the scale bar
    const clamped = Math.max(-100, Math.min(100, value));
    const pct = ((clamped + 100) / 200) * 100;
    regimePointer.style.left = `calc(${pct}% - 2px)`;
  }

  // ---- Regime Alert -------------------------------------------------------
  function updateRegimeAlert(data) {
    if (!regimeAlert) return;
    // Fetch alerts endpoint
    fetch("/api/elx/alerts")
      .then(r => r.json())
      .then(alertData => {
        const alert = alertData.current_alert;
        if (alert && alert.type !== "none") {
          regimeAlert.classList.remove("hidden", "alert-shift-up", "alert-shift-down");
          if (alert.type === "shift_up") {
            regimeAlert.classList.add("alert-shift-up");
            regimeAlert.innerHTML = `<span class="alert-icon">\u25B2</span> ${alert.message}`;
          } else if (alert.type === "shift_down") {
            regimeAlert.classList.add("alert-shift-down");
            regimeAlert.innerHTML = `<span class="alert-icon">\u25BC</span> ${alert.message}`;
          } else {
            regimeAlert.innerHTML = `<span class="alert-icon">\u25C9</span> ${alert.message}`;
          }
        } else {
          regimeAlert.classList.add("hidden");
        }
      })
      .catch(() => regimeAlert.classList.add("hidden"));
  }

  // ---- Fetch ELX ----------------------------------------------------------
  async function fetchELX() {
    try {
      const res = await fetch("/api/elx");
      const d = await res.json();

      animateValue(elxValueEl, d.value);
      updateRegimeMap(d.value);
      updateRegimeAlert(d);

      if (d.delta !== undefined) {
        const deltaSign = d.delta > 0 ? "+" : "";
        const deltaClass = d.delta > 0 ? "delta-up" : d.delta < 0 ? "delta-down" : "delta-flat";
        elxDeltaEl.textContent = `${deltaSign}${d.delta} today`;
        elxDeltaEl.className = "elx-delta " + deltaClass;
      } else {
        elxDeltaEl.textContent = "";
      }

      regimeLabel.textContent = d.regime;

      biasBadge.textContent = d.bias;
      biasBadge.className = "bias-badge";
      if (d.bias.includes("Risk-On")) biasBadge.classList.add("bias-green");
      else if (d.bias.includes("Risk-Off")) biasBadge.classList.add("bias-red");
      else biasBadge.classList.add("bias-orange");

      interpEl.textContent = d.interpretation;

      renderAssetBias(d.asset_bias || []);
      renderDrivers(d.drivers || []);

      document.body.classList.remove("loading");
    } catch (e) { console.error(e); }
  }

  // ---- Asset bias chips ---------------------------------------------------
  function renderAssetBias(biases) {
    assetBiasRow.innerHTML = "";
    biases.forEach((b) => {
      const arrow = b.direction === "up" ? "\u2191" : b.direction === "down" ? "\u2193" : "\u2192";
      const cls = b.direction === "up" ? "up" : b.direction === "down" ? "down" : "flat";
      const label = b.call || b.label || "";
      const chip = document.createElement("span");
      chip.className = "ab-chip";
      chip.innerHTML = `${b.asset} <span class="ab-arrow ${cls}">${arrow}</span> <span style="color:var(--text-3)">${label}</span>`;
      assetBiasRow.appendChild(chip);
    });
  }

  // ---- Drivers ------------------------------------------------------------
  function renderDrivers(drivers) {
    driversGrid.innerHTML = "";
    drivers.forEach((dr) => {
      const dir = dr.direction || "N/A";
      const isExp = dir === "Expansionary" || dir === "up";
      const isCon = dir === "Contractionary" || dir === "down";
      const ac = isExp ? "arrow-up" : isCon ? "arrow-down" : "arrow-flat";
      const ar = isExp ? "\u2191" : isCon ? "\u2193" : "\u2192";
      const signal = dr.signal || dr.direction || "\u2014";
      const weight = typeof dr.weight === "string" ? parseInt(dr.weight) : dr.weight;
      const card = document.createElement("div");
      card.className = "driver-card";
      card.innerHTML = `
        <div class="driver-name">${dr.name}</div>
        <div class="driver-score">${Number(dr.score).toFixed(1)}</div>
        <div class="driver-signal"><span class="arrow ${ac}">${ar}</span> ${signal}</div>
        <div class="driver-weight">${weight}% weight</div>
        <div class="weight-track"><div class="weight-fill" style="width:${weight * 2.5}%"></div></div>
      `;
      driversGrid.appendChild(card);
    });
  }

  // ---- Range selector -----------------------------------------------------
  function initRangeBar() {
    if (!rangeBar) return;
    const buttons = rangeBar.querySelectorAll(".range-btn");
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        buttons.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentRange = btn.dataset.range;
        fetchHistory(RANGE_DAYS[currentRange]);
        track("range_change", currentRange);
      });
    });
  }

  // ---- Fetch history ------------------------------------------------------
  async function fetchHistory(days) {
    days = days || RANGE_DAYS[currentRange] || 365;
    try {
      const res = await fetch(`/api/elx/history?days=${days}`);
      const data = await res.json();

      if (data.dates && data.values) {
        const series = data.dates.map((d, i) => ({ date: d, value: data.values[i] }));
        drawChart(series);
      }
    } catch (e) { console.error(e); }
  }

  // ---- 5-period moving average smoothing ----------------------------------
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

  // ---- Catmull-Rom spline helper ------------------------------------------
  function catmullRomPath(points, tension) {
    tension = tension || 0.20;
    let d = `M${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[Math.max(i - 1, 0)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(i + 2, points.length - 1)];
      d += ` C${(p1.x + (p2.x - p0.x) * tension).toFixed(2)},${(p1.y + (p2.y - p0.y) * tension).toFixed(2)} ${(p2.x - (p3.x - p1.x) * tension).toFixed(2)},${(p2.y - (p3.y - p1.y) * tension).toFixed(2)} ${p2.x.toFixed(2)},${p2.y.toFixed(2)}`;
    }
    return d;
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

    const minV = Math.min(...smoothed) - 6;
    const maxV = Math.max(...smoothed) + 6;
    const rV = maxV - minV || 1;

    const pts = smoothed.map((v, i) => ({
      x: P.l + (i / (series.length - 1)) * pW,
      y: P.t + pH - ((v - minV) / rV) * pH,
      v: v,
    }));

    // Downsample for smoothness
    const step = series.length > 1000 ? 5 : series.length > 300 ? 3 : 2;
    const sampled = [];
    for (let i = 0; i < pts.length; i += step) sampled.push(pts[i]);
    if (sampled[sampled.length - 1] !== pts[pts.length - 1]) sampled.push(pts[pts.length - 1]);

    const linePath = catmullRomPath(sampled);
    const areaPath = linePath
      + ` L${sampled[sampled.length - 1].x.toFixed(2)},${(P.t + pH).toFixed(2)}`
      + ` L${sampled[0].x.toFixed(2)},${(P.t + pH).toFixed(2)} Z`;

    const last = pts[pts.length - 1];
    const accent = last.v >= 20 ? "#30d158" : last.v >= -20 ? "#ff9f0a" : "#ff453a";
    const rgb = last.v >= 20 ? "48,209,88" : last.v >= -20 ? "255,159,10" : "255,69,58";

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
    const labelCount = 7;
    const labelStep = Math.max(1, Math.floor(series.length / labelCount));
    for (let i = 0; i < series.length; i += labelStep) {
      const p = pts[i];
      if (!p) continue;
      const dt = new Date(series[i].date + "T00:00:00");
      let label;
      if (series.length > 1000) {
        label = dt.getFullYear().toString();
      } else {
        label = dt.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
      }
      xL += `<text x="${p.x.toFixed(1)}" y="${(H - 12).toFixed(1)}" text-anchor="middle" fill="#c7c7cc" font-size="10" font-weight="500" font-family="Inter,-apple-system,sans-serif">${label}</text>`;
    }

    // Zero line
    let zeroLine = "";
    if (minV < 0 && maxV > 0) {
      const zeroY = P.t + pH - ((0 - minV) / rV) * pH;
      zeroLine = `<line x1="${P.l}" y1="${zeroY.toFixed(1)}" x2="${W - P.r}" y2="${zeroY.toFixed(1)}" stroke="rgba(0,0,0,.08)" stroke-width="1" stroke-dasharray="4,4"/>`;
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
          <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="b"/>
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

      ${grid}${yL}${xL}${zeroLine}

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

  // ---- Fetch Markets with Overlay Charts -----------------------------------
  async function fetchMarkets() {
    try {
      const res = await fetch("/api/elx/markets");
      const data = await res.json();

      // Also fetch 90d ELX history for overlay
      const histRes = await fetch("/api/elx/history?days=90");
      const histData = await histRes.json();
      elxHistory90 = histData;

      if (Array.isArray(data)) {
        renderCorrStripV2(data);
        renderMarketsOverlay(data);
      }
    } catch (e) { console.error(e); }
  }

  // ---- Correlation strip ---------------------------------------------------
  function renderCorrStripV2(markets) {
    if (!corrStrip) return;
    const labelMap = { "S&P 500": "SPX", "Gold": "Gold", "Bitcoin": "BTC", "US Dollar": "DXY" };
    let html = "";
    markets.forEach((m) => {
      const label = labelMap[m.name] || m.ticker || m.name;
      const sign = m.correlation > 0 ? "+" : "";
      const cls = m.correlation > 0.15 ? "corr-pos" : m.correlation < -0.15 ? "corr-neg" : "corr-neu";
      html += `<span class="corr-item ${cls}"><span class="corr-label">${label}</span><span class="corr-val">${sign}${m.correlation.toFixed(2)}</span></span>`;
    });
    corrStrip.innerHTML = `<span class="corr-title">ELX Correlation (90d)</span>` + html;
  }

  // ---- Markets with overlay charts (ELX line + Market line) ----------------
  function renderMarketsOverlay(markets) {
    marketsGrid.innerHTML = "";
    const labelMap = { "S&P 500": "SPX", "Gold": "Gold", "Bitcoin": "BTC", "US Dollar": "DXY" };

    markets.forEach((m) => {
      const cc = m.change_30d > 0.5 ? "change-up" : m.change_30d < -0.5 ? "change-down" : "change-flat";
      const cs = m.change_30d > 0 ? "+" : "";
      const corrS = m.correlation > 0 ? "+" : "";

      let priceStr;
      if (m.price >= 10000) priceStr = m.price.toLocaleString("en-US", { maximumFractionDigits: 0 });
      else if (m.price >= 100) priceStr = m.price.toLocaleString("en-US", { maximumFractionDigits: 1 });
      else priceStr = m.price.toFixed(2);

      const card = document.createElement("div");
      card.className = "market-card";
      const sparkId = `spark-${m.name.replace(/[^a-zA-Z0-9]/g, "")}`;
      const shortName = labelMap[m.name] || m.name;
      card.innerHTML = `
        <div class="market-header">
          <span class="market-ticker">${m.name}</span>
          <span class="market-corr">\u03C1 ${corrS}${m.correlation.toFixed(2)}</span>
        </div>
        <div class="market-price">${priceStr}</div>
        <div class="market-change ${cc}">${cs}${m.change_30d}% \u00B7 30d</div>
        <div class="market-spark" id="${sparkId}"></div>
        <div class="market-overlay-legend">
          <span class="legend-item"><span class="legend-dot dot-elx"></span>ELX</span>
          <span class="legend-item"><span class="legend-dot dot-market"></span>${shortName}</span>
        </div>
      `;
      marketsGrid.appendChild(card);
      drawOverlayChart(sparkId, m.series, m.change_30d);
    });
  }

  // ---- Overlay chart: ELX (gray) + Market (colored) on same axes ----------
  function drawOverlayChart(id, marketData, change) {
    const el = document.getElementById(id);
    if (!el || !marketData || marketData.length < 2) return;

    const W = 280, H = 80;
    const color = change > 0.5 ? "#30d158" : change < -0.5 ? "#ff453a" : "#ff9f0a";
    const rgb = change > 0.5 ? "48,209,88" : change < -0.5 ? "255,69,58" : "255,159,10";

    // Normalize market data to 0-1
    const mMin = Math.min(...marketData);
    const mMax = Math.max(...marketData);
    const mRange = mMax - mMin || 1;
    const mNorm = marketData.map(v => (v - mMin) / mRange);

    // Normalize ELX data to 0-1 (match length to market data)
    let elxNorm = [];
    if (elxHistory90 && elxHistory90.values && elxHistory90.values.length > 0) {
      const elxVals = elxHistory90.values;
      const eMin = Math.min(...elxVals);
      const eMax = Math.max(...elxVals);
      const eRange = eMax - eMin || 1;
      // Resample ELX to match market data length
      const elxResampled = [];
      for (let i = 0; i < marketData.length; i++) {
        const idx = Math.floor((i / marketData.length) * elxVals.length);
        elxResampled.push(elxVals[Math.min(idx, elxVals.length - 1)]);
      }
      elxNorm = elxResampled.map(v => (v - eMin) / eRange);
    }

    // Build market line points
    const mPts = mNorm.map((v, i) => ({
      x: (i / (mNorm.length - 1)) * W,
      y: H - 4 - v * (H - 8),
    }));

    const marketPath = catmullRomPath(mPts, 0.22);
    const marketArea = marketPath + ` L${W},${H} L0,${H} Z`;

    // Build ELX line points (if available)
    let elxPath = "";
    if (elxNorm.length > 0) {
      const ePts = elxNorm.map((v, i) => ({
        x: (i / (elxNorm.length - 1)) * W,
        y: H - 4 - v * (H - 8),
      }));
      elxPath = catmullRomPath(ePts, 0.22);
    }

    el.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="og-${id}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(${rgb},.12)"/>
          <stop offset="100%" stop-color="rgba(${rgb},0)"/>
        </linearGradient>
      </defs>
      <path d="${marketArea}" fill="url(#og-${id})"/>
      ${elxPath ? `<path d="${elxPath}" fill="none" stroke="#86868b" stroke-width="1" stroke-linecap="round" opacity=".4" stroke-dasharray="3,3"/>` : ""}
      <path d="${marketPath}" fill="none" stroke="${color}" stroke-width="1.4" stroke-linecap="round"/>
    </svg>`;
  }

  // ---- Share button -------------------------------------------------------
  function initShare() {
    if (!shareBtn) return;
    shareBtn.addEventListener("click", async () => {
      shareBtn.classList.add("sharing");
      shareBtn.textContent = "Generating...";
      track("share_click");
      try {
        const res = await fetch("/api/elx/share");
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);

        if (navigator.share && navigator.canShare) {
          const file = new File([blob], "elx-share.png", { type: "image/png" });
          try {
            await navigator.share({ files: [file], title: "ELX \u2014 Earth Liquidity Index" });
          } catch (shareErr) {
            downloadBlob(url);
          }
        } else {
          downloadBlob(url);
        }
      } catch (e) {
        console.error(e);
      }
      shareBtn.classList.remove("sharing");
      shareBtn.innerHTML = `<span class="share-icon">\u2197</span> Share ELX`;
    });
  }

  function downloadBlob(url) {
    const a = document.createElement("a");
    a.href = url;
    a.download = "elx-share.png";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ---- Subscribe form -----------------------------------------------------
  function initSubscribe() {
    const form = document.getElementById("subscribe-form");
    const input = document.getElementById("subscribe-email");
    const btn = document.getElementById("subscribe-btn");
    const msg = document.getElementById("subscribe-msg");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = input.value.trim();
      if (!email) return;

      btn.textContent = "...";
      btn.disabled = true;

      try {
        const res = await fetch("/api/subscribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, source: "homepage" }),
        });
        const data = await res.json();

        if (data.ok) {
          btn.textContent = "Subscribed";
          btn.classList.add("success");
          msg.textContent = "You'll receive the daily ELX update.";
          msg.style.color = "var(--green)";
          input.value = "";
        } else {
          btn.textContent = data.error === "Already subscribed" ? "Already subscribed" : "Try again";
          btn.classList.add(data.error === "Already subscribed" ? "success" : "error");
          msg.textContent = data.error || "Something went wrong.";
          msg.style.color = data.error === "Already subscribed" ? "var(--green)" : "var(--red)";
        }
      } catch (err) {
        btn.textContent = "Error";
        btn.classList.add("error");
        msg.textContent = "Network error. Please try again.";
        msg.style.color = "var(--red)";
      }

      setTimeout(() => {
        btn.textContent = "Subscribe";
        btn.disabled = false;
        btn.classList.remove("success", "error");
      }, 3000);
    });
  }

  // ---- Analytics tracking --------------------------------------------------
  function track(event, meta) {
    try {
      fetch("/api/track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event, meta: meta || "" }),
      });
    } catch (e) { /* silent */ }
  }

  // ---- Init ---------------------------------------------------------------
  setDate();
  fetchELX();
  fetchHistory();
  fetchMarkets();
  initRangeBar();
  initShare();
  initSubscribe();
})();
