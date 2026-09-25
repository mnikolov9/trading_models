"""Генерира статично уеб табло (site/index.html) от reports/results.json за GitHub Pages."""
import json
import os
import shutil

import config

TEMPLATE = r"""<!doctype html>
<html lang="bg">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading модели</title>
<style>
:root{color-scheme:light;--bg:#f6f6f4;--surface:#fcfcfb;--border:#e4e3df;--text:#0b0b0b;--text2:#52514e;--muted:#8a8984;
 --s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--base:#9a9993;--pos-bg:rgba(42,120,214,.16);--neg-bg:rgba(235,104,52,.18);--good:#008300;--bad:#c2410c;--warn:#b77900}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#111110;--surface:#1a1a19;--border:#2e2e2c;--text:#fff;--text2:#c3c2b7;--muted:#8d8c86;
 --s1:#3987e5;--s2:#d95926;--s3:#199e70;--base:#7a7973;--pos-bg:rgba(57,135,229,.25);--neg-bg:rgba(217,89,38,.28);--good:#4cb34c;--bad:#f07a4a;--warn:#e0a526}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:0 0 12px}
.sub{color:var(--text2);font-size:13px}
.banner{margin:16px 0;padding:10px 14px;border-radius:8px;border:1px solid var(--warn);color:var(--text);font-size:14px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}
.tile,.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px}
.tile .k{color:var(--text2);font-size:13px}.tile .v{font-size:28px;font-weight:650;font-variant-numeric:tabular-nums;margin-top:2px}
.tile .n{color:var(--muted);font-size:12px}
.card{margin-top:16px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--border);white-space:nowrap}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
th{color:var(--text2);font-weight:550;font-size:13px}
tr.bh td{color:var(--text2)}tr.port td{font-weight:650}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:13px;font-weight:600;border:1px solid currentColor}
.buy{color:var(--good)}.cash{color:var(--text2)}
.chartbox{position:relative;height:340px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;color:var(--text2);margin-bottom:8px}
.legend span{white-space:nowrap}.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin-right:6px}
.hm td{text-align:center;min-width:52px;font-size:13px}.hm td:first-child{text-align:left;font-weight:600}
.note{color:var(--muted);font-size:12px;margin-top:24px}
@media (max-width:760px){.grid{grid-template-columns:repeat(2,1fr)}.tile .v{font-size:22px}.chartbox{height:260px}}
</style>
</head>
<body>
<main>
<h1>Модели за акции, злато и крипто</h1>
<div class="sub" id="meta"></div>
<div id="banner"></div>
<div class="grid" id="tiles"></div>

<div class="card"><h2>Сигнали за днес</h2><table id="signals"></table></div>

<div class="card">
 <h2>Растеж на 100 € (портфейл, out-of-sample, логаритмична скала)</h2>
 <div class="legend" id="legend"></div>
 <div class="chartbox" id="eq"></div>
</div>

<div class="card"><h2>Резултати по активи и стратегии</h2><p class="sub" style="margin:-6px 0 10px">„Базова точност“ = колко често би познал, ако винаги казваш „нагоре“. Моделът има стойност само ако е над нея. „Без модел“ показва същия контрол на риска без прогнози.</p><table id="summary"></table></div>
<div class="card"><h2>Месечни резултати на портфейла</h2><table class="hm" id="monthly"></table></div>

<p class="note">Резултатите са от backtest с walk-forward валидация: моделът прогнозира всеки период само с минали данни, а комисионните са включени. Миналите резултати не гарантират бъдещи. Образователен проект, не е финансов съвет.</p>
</main>
<script>
const D = __DATA__;
const MAIN = D.main_strategy;
const pct = (v, d=1) => v == null ? "–" : (v*100).toFixed(d).replace(".", ",") + "%";
const num = (v, d=2) => v == null ? "–" : v.toFixed(d).replace(".", ",");
const esc = s => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

document.getElementById("meta").textContent =
  `Обновено: ${D.generated_utc} · стратегия: ${MAIN} · модел: ${D.model} · хоризонт: ${D.horizon} дни · цел: ${D.target[0]*100}–${D.target[1]*100}% годишно`;
if (D.synthetic) document.getElementById("banner").innerHTML =
  '<div class="banner">Това са ТЕСТОВИ изкуствени данни. Реалните резултати ще се появят след първото пускане в GitHub Actions.</div>';

const port = D.summary.find(r => r["Актив"] === "ПОРТФЕЙЛ" && r["Стратегия"] === MAIN);
const portBH = D.summary.find(r => r["Актив"] === "ПОРТФЕЙЛ" && r["Стратегия"] === "Купи и дръж");
const NAMES = Object.keys(D.equity.series);
const COLOR = {}; let ci = 1;
NAMES.forEach(n => { COLOR[n] = n === "Купи и дръж" ? "var(--base)" : (n === MAIN ? "var(--s1)" : `var(--s${++ci})`); });
const cagr = port["Годишна доходност"], [lo, hi] = D.target;
const status = cagr >= lo && cagr <= hi ? ["в целта", "var(--good)"] :
               cagr > hi ? ["над целта: провери!", "var(--warn)"] : ["под целта", "var(--bad)"];
const tiles = [
  ["Годишна доходност", pct(cagr), `<span style="color:${status[1]}">● ${status[0]}</span> · купи и дръж ${pct(portBH["Годишна доходност"])}`],
  ["Средно на месец", pct(port["Средно на месец"], 2), `печеливши месеци ${pct(port["Печеливши месеци"], 0)}`],
  ["Макс. спад", pct(port["Макс. спад"]), `купи и дръж ${pct(portBH["Макс. спад"])}`],
  ["Sharpe", num(port["Sharpe"]), `купи и дръж ${num(portBH["Sharpe"])}`],
];
document.getElementById("tiles").innerHTML = tiles.map(([k, v, n]) =>
  `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join("");

document.getElementById("signals").innerHTML =
  "<tr><th>Актив</th><th>Сигнал</th><th>Вероятност за ръст</th><th>Дял от капитала</th><th>Данни към</th></tr>" +
  D.signals.map(s => {
    const buy = s["Позиция (дял от капитала)"] > 0;
    return `<tr><td>${esc(s["Актив"])}</td><td><span class="pill ${buy ? "buy" : "cash"}">${buy ? "▲ Купи/дръж" : "■ Кеш"}</span></td>
      <td>${pct(s["Вероятност за ръст"])}</td><td>${pct(s["Позиция (дял от капитала)"], 0)}</td><td>${esc(s["Дата"])}</td></tr>`;
  }).join("");

const cols = ["Годишна доходност","Средно на месец","Волатилност","Sharpe","Макс. спад","Печеливши месеци","Точност (посока)","Базова точност","В пазара"];
document.getElementById("summary").innerHTML =
  "<tr><th>Актив</th><th>Стратегия</th>" + cols.map(c => `<th>${c}</th>`).join("") + "</tr>" +
  D.summary.map(r => {
    const cls = (r["Стратегия"] !== MAIN ? "bh " : "") + (r["Актив"] === "ПОРТФЕЙЛ" ? "port" : "");
    return `<tr class="${cls}"><td>${esc(r["Актив"])}</td><td>${esc(r["Стратегия"])}</td>` +
      cols.map(c => `<td>${c === "Sharpe" ? num(r[c]) : pct(r[c])}</td>`).join("") + "</tr>";
  }).join("");

const months = ["Яну","Фев","Мар","Апр","Май","Юни","Юли","Авг","Сеп","Окт","Ное","Дек"];
const byYear = {};
Object.entries(D.monthly).forEach(([ym, v]) => { const [y, m] = ym.split("-"); (byYear[y] ??= {})[+m] = v; });
const cell = v => {
  if (v == null) return "<td></td>";
  const a = Math.min(Math.abs(v) / 0.06, 1);
  const bg = v >= 0 ? "var(--pos-bg)" : "var(--neg-bg)";
  return `<td style="background:color-mix(in srgb, ${bg} ${Math.round(a*100)}%, transparent)" title="${pct(v,2)}">${pct(v)}</td>`;
};
document.getElementById("monthly").innerHTML =
  "<tr><th>Година</th>" + months.map(m => `<th>${m}</th>`).join("") + "<th>Общо</th></tr>" +
  Object.keys(byYear).sort().reverse().map(y => {
    const vals = byYear[y]; const tot = Object.values(vals).reduce((a, v) => a * (1 + v), 1) - 1;
    return `<tr><td>${y}</td>` + months.map((_, i) => cell(vals[i+1])).join("") + `<td><b>${pct(tot)}</b></td></tr>`;
  }).join("");

// Линейна графика на чист SVG (без външни библиотеки), логаритмична скала
document.getElementById("legend").innerHTML = NAMES.map(n =>
  `<span><i style="background:${COLOR[n]}"></i>${esc(n)}</span>`).join("");
(function () {
  const box = document.getElementById("eq"), E = D.equity, n = E.dates.length;
  if (!n) return;
  const W = box.clientWidth || 800, H = box.clientHeight || 300, m = {l: 64, r: 12, t: 10, b: 26};
  const all = NAMES.flatMap(k => E.series[k]).filter(v => v > 0);
  const lo = Math.log(Math.min(...all) * 0.95), hi = Math.log(Math.max(...all) * 1.05);
  const X = i => m.l + (W - m.l - m.r) * i / Math.max(n - 1, 1);
  const Y = v => H - m.b - (H - m.t - m.b) * (Math.log(v) - lo) / ((hi - lo) || 1);
  const path = arr => arr.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1)).join("");
  let g = "";
  const cand = [];
  for (let e = 0; e < 7; e++) [1, 2, 5].forEach(k => cand.push(k * Math.pow(10, e)));
  let ticks = cand.filter(v => Math.log(v) >= lo && Math.log(v) <= hi);
  if (ticks.length > 7) ticks = ticks.filter((_, i) => i % 2 === 0);
  ticks.forEach(v => { const y = Y(v);
    g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="var(--border)"/>` +
         `<text x="${m.l - 8}" y="${y + 4}" text-anchor="end" fill="var(--text2)" font-size="12">${v.toLocaleString("bg-BG")} €</text>`; });
  let lastYear = "", lastX = -1e9;
  E.dates.forEach((d, i) => {
    const yr = d.slice(0, 4);
    if (yr !== lastYear) { lastYear = yr; if (X(i) - lastX < 44) return; lastX = X(i);
      g += `<text x="${X(i)}" y="${H - 6}" text-anchor="middle" fill="var(--text2)" font-size="12">${yr}</text>`; }
  });
  const order = NAMES.slice().sort((a, b) => (a === MAIN) - (b === MAIN));   // основната стратегия най-отгоре
  const lines = order.map(k => `<path d="${path(E.series[k])}" fill="none" stroke="${COLOR[k]}" stroke-width="${k === MAIN ? 2.5 : 1.75}" stroke-linejoin="round"/>`).join("");
  const dots = NAMES.map((k, j) => `<circle data-k="${j}" r="4.5" fill="${COLOR[k]}" stroke="var(--surface)" stroke-width="2" visibility="hidden"/>`).join("");
  box.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="Растеж на 100 евро по стратегии">${g}${lines}
    <line id="xh" y1="${m.t}" y2="${H - m.b}" stroke="var(--muted)" stroke-dasharray="3 3" visibility="hidden"/>${dots}
    <rect x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent" id="hit"/></svg>
    <div id="tip" style="position:absolute;pointer-events:none;display:none;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:13px;box-shadow:0 4px 14px rgba(0,0,0,.15);white-space:nowrap"></div>`;
  const svg = box.querySelector("svg"), tip = box.querySelector("#tip"), xh = svg.querySelector("#xh");
  const show = ev => {
    const r = svg.getBoundingClientRect(), px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
    const i = Math.max(0, Math.min(n - 1, Math.round((px - m.l) / (W - m.l - m.r) * (n - 1))));
    const x = X(i);
    xh.setAttribute("x1", x); xh.setAttribute("x2", x); xh.setAttribute("visibility", "visible");
    NAMES.forEach((k, j) => { const c = svg.querySelector(`circle[data-k="${j}"]`);
      c.setAttribute("cx", x); c.setAttribute("cy", Y(E.series[k][i])); c.setAttribute("visibility", "visible"); });
    tip.innerHTML = `<div style="color:var(--text2)">${E.dates[i]}</div>` + NAMES.map(k =>
      `<div><span style="color:${COLOR[k]}">━</span> ${esc(k)}: <b>${Math.round(E.series[k][i]).toLocaleString("bg-BG")} €</b></div>`).join("");
    tip.style.display = "block";
    tip.style.left = Math.max(0, Math.min(x + 12, W - tip.offsetWidth - 4)) + "px"; tip.style.top = "12px";
  };
  const hide = () => { tip.style.display = "none";
    svg.querySelectorAll("#xh,circle").forEach(e => e.setAttribute("visibility", "hidden")); };
  const hit = svg.querySelector("#hit");
  hit.addEventListener("mousemove", show); hit.addEventListener("touchmove", show, {passive: true});
  hit.addEventListener("mouseleave", hide); hit.addEventListener("touchend", hide);
})();
</script>
</body>
</html>
"""


def build(out_dir: str = "site") -> str:
    with open(os.path.join(config.REPORT_DIR, "results.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    os.makedirs(out_dir, exist_ok=True)
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    # сурови отчети за сваляне
    for name in ("summary.csv", "monthly_returns.csv", "latest_signals.csv", "results.json"):
        src = os.path.join(config.REPORT_DIR, name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out_dir, name))
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    print(f"Таблото е генерирано: {path}")
    return path


if __name__ == "__main__":
    build()
