"""Топ 50 компании: движение на акциите + общ (pooled) модел, който ги подрежда.

Идея: вместо да гадаем дали пазарът ще расте, моделът сравнява акциите помежду им
и избира тези с най-голям шанс да се представят ПО-ДОБРЕ от средното за следващите
TOP50_HORIZON дни. Всяка седмица държим TOP_K акции с най-висока оценка.
Сравняваме с равни тегла във всички 50 (същата вселена).

ВНИМАНИЕ (survivorship bias): списъкът е днешният топ 50, т.е. компании, за които вече
знаем, че са станали огромни. Затова backtest-ът и на модела, и на сравнението изглежда
по-добре, отколкото би бил в реалността. Честната оценка е РАЗЛИКАТА модел - равни тегла.
"""
import numpy as np
import pandas as pd

import backtest as bt
import config
import data
import features
import model as mdl
from universe import TOP50, ALT

TOP50_HORIZON = 21      # прогноза за ~1 месец напред
REBALANCE_EVERY = 5     # преразпределение всяка седмица
TOP_K = 10              # колко акции държим
RETRAIN_EVERY = 63      # преобучение на ~3 месеца (моделът е общ и по-бавен)
COST_BPS = 5


def load(market: pd.DataFrame, synthetic: bool, refresh: bool) -> tuple[dict, list]:
    prices, missing = {}, []
    for i, (t, name, _) in enumerate(TOP50):
        df = None
        for tk in [t] + ([ALT[t]] if t in ALT else []):
            try:
                if synthetic:
                    df = data.synthetic(t, n_days=1500 + 20 * (i % 10), seed=500 + i, vol=0.018,
                                        drift=0.0004, signal=0.05)
                else:
                    df = data.download(tk, refresh=refresh)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"{tk} ({name}): няма данни ({exc})")
        if df is None or df.empty:
            missing.append(f"{name} ({t})")
            continue
        # общ календар = търговските дни на американския пазар
        prices[t] = df.reindex(market.index, method="ffill", limit=5).dropna()
    return prices, missing


def movement_table(prices: dict, probs_last: pd.Series) -> list:
    names = {t: (n, c) for t, n, c in TOP50}
    rows = []
    for t, df in prices.items():
        c = df["close"]
        if len(c) < 2:
            continue
        last = c.iloc[-1]

        def chg(n):
            return float(last / c.iloc[-1 - n] - 1) if len(c) > n else None
        year_start = c[c.index.year == c.index[-1].year]
        rows.append({
            "ticker": t, "name": names[t][0], "country": names[t][1],
            "date": c.index[-1].strftime("%Y-%m-%d"), "close": round(float(last), 2),
            "d1": chg(1), "w1": chg(5), "m1": chg(21), "m3": chg(63), "y1": chg(252),
            "ytd": float(last / year_start.iloc[0] - 1) if len(year_start) else None,
            "prob": None if pd.isna(probs_last.get(t, np.nan)) else float(probs_last[t]),
        })
    ranked = sorted([r for r in rows if r["prob"] is not None], key=lambda r: -r["prob"])
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    return rows


def run(market: pd.DataFrame, synthetic: bool = False, refresh: bool = False, model_kind: str = "gbm",
        macro: dict | None = None) -> dict:
    prices, missing = load(market, synthetic, refresh)
    print(f"Топ 50: заредени {len(prices)} акции")

    # Панел (дата, акция) -> признаци + цел
    feats, fwd = {}, {}
    for t, df in prices.items():
        f = features.build_features(df, market.reindex(df.index), macro)
        feats[t] = f
        fwd[t] = features.build_target(df, TOP50_HORIZON)
    X = pd.concat(feats, names=["ticker", "date"]).swaplevel().sort_index()
    R = pd.concat(fwd, names=["ticker", "date"]).swaplevel().sort_index()

    # Признаци спрямо останалите акции в същия ден (ранг 0..1)
    for col in ("ret_5", "ret_21", "ret_63", "ret_126", "vol_63", "dist_ma200", "drawdown_252"):
        X[f"xs_{col}"] = X[col].groupby(level="date").rank(pct=True)
    # Цел: по-добре ли ще се представи от медианата на акциите в този ден
    rel = R - R.groupby(level="date").transform("median")
    rel[R.isna()] = np.nan

    dates = X.index.get_level_values("date").unique().sort_values()
    probs = pd.Series(np.nan, index=X.index)
    start_i = min(config.MIN_TRAIN_DAYS, len(dates) // 2)
    valid_x = X.notna().mean(axis=1) > 0.8
    date_level = X.index.get_level_values("date")

    for s in range(start_i, len(dates), RETRAIN_EVERY):
        train_end = dates[s - TOP50_HORIZON]          # embargo = хоризонта
        tr = (date_level < train_end) & valid_x.values & rel.notna().values
        if tr.sum() < 5000:
            continue
        te_dates = dates[s:s + RETRAIN_EVERY]
        te = date_level.isin(te_dates) & valid_x.values
        m = mdl.make_model(model_kind)
        Xtr, Xte = X[tr], X[te]
        if model_kind != "logreg" and not mdl.HAS_LGBM:
            med = Xtr.median()
            Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
        m.fit(Xtr, (rel[tr] > 0).astype(int))
        probs[te] = m.predict_proba(Xte)[:, 1]

    P = probs.unstack("ticker")
    daily = pd.DataFrame({t: df["close"].pct_change() for t, df in prices.items()}).reindex(P.index)

    # Седмично преразпределение: топ K по вероятност срещу равни тегла във всички с прогноза
    w_model = pd.DataFrame(0.0, index=P.index, columns=P.columns)
    w_eq = w_model.copy()
    rebal = P.dropna(how="all").index[::REBALANCE_EVERY]
    for d in rebal:
        row = P.loc[d].dropna()
        if len(row) < TOP_K * 2:
            continue
        w_model.loc[d, row.nlargest(TOP_K).index] = 1.0 / TOP_K
        w_eq.loc[d, row.index] = 1.0 / len(row)
    for w in (w_model, w_eq):
        w[~w.index.isin(rebal)] = np.nan
        w.ffill(inplace=True)
        w.fillna(0.0, inplace=True)
    first = w_model.sum(axis=1).gt(0).idxmax()

    def perf(w):
        held = w.shift(1).fillna(0.0)
        gross = (held * daily.fillna(0.0)).sum(axis=1)
        cost = w.diff().abs().sum(axis=1).fillna(0.0) * COST_BPS / 1e4
        return (gross - cost.shift(1).fillna(0.0)).loc[first:]

    r_model, r_eq = perf(w_model), perf(w_eq)
    r_spy = market["close"].pct_change().reindex(r_model.index).fillna(0.0)
    series = {f"Модел (топ {TOP_K})": r_model, "Равни тегла (всички 50)": r_eq, "S&P 500": r_spy}

    summary = [{"Стратегия": k, **bt.metrics(v, 252)} for k, v in series.items()]
    hit = None
    both = P.stack().to_frame("p").join(rel.rename("r")).dropna()
    if len(both):
        hit = float(((both["p"] > 0.5) == (both["r"] > 0)).mean())

    eq = pd.DataFrame({k: (1 + v).cumprod() * 100 for k, v in series.items()}).resample("W").last().dropna()
    last_probs = P.ffill(limit=10).iloc[-1] if len(P) else pd.Series(dtype=float)
    table = movement_table(prices, last_probs)

    for r in summary:
        print(f"  {r['Стратегия']:<26} {r['Годишна доходност']:7.1%} годишно, спад {r['Макс. спад']:6.1%}, Sharpe {r['Sharpe']:.2f}")
    return {
        "top_k": TOP_K, "horizon": TOP50_HORIZON, "n_stocks": len(prices), "missing": missing, "hit_rate": hit,
        "summary": summary, "table": table,
        "equity": {"dates": [d.strftime("%Y-%m-%d") for d in eq.index],
                   "series": {k: [round(float(v), 2) for v in eq[k]] for k in eq}},
        "main": f"Модел (топ {TOP_K})",
    }
