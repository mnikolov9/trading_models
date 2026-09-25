"""Главен скрипт: данни -> признаци -> walk-forward модел -> backtest -> отчет.

Примери:
    python run.py                  # реални данни от Yahoo Finance
    python run.py --refresh        # изтегли данните наново
    python run.py --model logreg   # базов модел за сравнение
    python run.py --synthetic      # тест без интернет, с изкуствени данни
"""
import argparse
import os

import numpy as np
import pandas as pd

import backtest as bt
import config
import data
import features
import model as mdl


def load(synthetic: bool, refresh: bool) -> dict:
    if not synthetic:
        return data.load_all(refresh=refresh)
    out = {}
    for i, t in enumerate(config.ASSETS):
        crypto = t.endswith("-USD")
        out[t] = data.synthetic(t, n_days=3500 if crypto else 2500, seed=i,
                                weekdays_only=not crypto, vol=0.035 if crypto else 0.011,
                                drift=0.0008 if crypto else 0.0003, signal=0.08)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--model", default="gbm", choices=["gbm", "logreg"])
    ap.add_argument("--no-top50", action="store_true", help="без модула за топ 50 компании")
    args = ap.parse_args()

    os.makedirs(config.REPORT_DIR, exist_ok=True)
    prices = load(args.synthetic, args.refresh)
    market = prices.get(config.MARKET_TICKER)

    rows, signals = [], []
    names = list(config.STRATEGIES) + ["Купи и дръж"]
    rets = {n: {} for n in names}
    main_name = config.MAIN_STRATEGY
    print(f"Модел: {args.model} ({'LightGBM' if mdl.HAS_LGBM else 'sklearn HistGradientBoosting'})"
          if args.model == "gbm" else "Модел: logistic regression")

    for t, df in prices.items():
        mkt = None if t == config.MARKET_TICKER else market
        X = features.build_features(df, mkt)
        fwd = features.build_target(df, config.HORIZON)
        probs = mdl.walk_forward(X, fwd, config.HORIZON, config.MIN_TRAIN_DAYS,
                                 config.RETRAIN_EVERY, args.model)
        oos = probs.first_valid_index()
        acc, base = bt.hit_rate(probs, fwd)
        cost = config.COST_BPS.get(t, 10)

        for name, strat in config.STRATEGIES.items():
            pos = bt.positions_from_probs(probs, df["close"], strat, config.MAX_LEVERAGE)
            sr = bt.run(pos, df["close"], cost).loc[oos:]
            rets[name][t] = sr
            extra = {"В пазара": (pos.loc[oos:] > 0).mean()}
            if strat["mode"] != "always":
                extra.update({"Точност (посока)": acc, "Базова точност": base})
            rows.append({"Актив": config.ASSETS[t], "Стратегия": name, **bt.metrics(sr), **extra})
            if name == main_name:
                signals.append({"Актив": config.ASSETS[t], "Дата": df.index[-1].date(),
                                "Вероятност за ръст": probs.iloc[-1], "Позиция (дял от капитала)": pos.iloc[-1]})

        bh = df["close"].pct_change().loc[oos:].fillna(0.0)
        rets["Купи и дръж"][t] = bh
        rows.append({"Актив": config.ASSETS[t], "Стратегия": "Купи и дръж", **bt.metrics(bh)})

    port = {n: bt.portfolio(rets[n]) for n in names}
    for n in names:
        rows.append({"Актив": "ПОРТФЕЙЛ", "Стратегия": n, **bt.metrics(port[n])})
    p_main = port[main_name]

    report = pd.DataFrame(rows)
    report.to_csv(os.path.join(config.REPORT_DIR, "summary.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(signals).to_csv(os.path.join(config.REPORT_DIR, "latest_signals.csv"), index=False, encoding="utf-8-sig")
    monthly = (1 + p_main).resample("ME").prod() - 1
    monthly.to_frame(f"Портфейл ({main_name})").to_csv(os.path.join(config.REPORT_DIR, "monthly_returns.csv"), encoding="utf-8-sig")

    pct = ["Годишна доходност", "Средно на месец", "Волатилност", "Макс. спад", "Печеливши месеци",
           "Най-лош месец", "Точност (посока)", "Базова точност", "В пазара"]
    show = report.drop(columns=["Най-лош месец"]).copy()
    for col in pct:
        if col in show:
            show[col] = show[col].map(lambda v: "" if pd.isna(v) else f"{v:.1%}")
    show["Sharpe"] = show["Sharpe"].map(lambda v: f"{v:.2f}")
    show["Години"] = show["Години"].map(lambda v: f"{v:.1f}")
    pd.set_option("display.width", 250, "display.max_columns", 20)
    print("\n" + show.to_string(index=False))

    cagr = bt.metrics(p_main)["Годишна доходност"]
    lo, hi = config.TARGET_ANNUAL_RETURN
    verdict = "в целта" if lo <= cagr <= hi else ("над целта (провери за грешки!)" if cagr > hi else "под целта")
    print(f"\nПортфейл ({main_name}): {cagr:.1%} годишно -> {verdict} ({lo:.0%}-{hi:.0%})")
    print("\nПоследни сигнали:\n" + pd.DataFrame(signals).to_string(index=False))

    # Данни за уеб таблото (dashboard.py)
    import json
    from datetime import datetime, timezone

    def clean(v):
        if isinstance(v, (float, np.floating)):
            return None if not np.isfinite(v) else round(float(v), 6)
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return v

    eq = pd.DataFrame({n: (1 + port[n]).cumprod() * 100 for n in names}).resample("W").last().dropna()
    results = {
        "version": "0.2",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "synthetic": args.synthetic,
        "model": ("LightGBM" if mdl.HAS_LGBM else "HistGradientBoosting") if args.model == "gbm" else "Logistic regression",
        "horizon": config.HORIZON,
        "main_strategy": main_name,
        "strategies": config.STRATEGIES,
        "target": list(config.TARGET_ANNUAL_RETURN),
        "summary": [{k: clean(v) for k, v in r.items()} for r in rows],
        "signals": [{k: clean(v) for k, v in s.items()} for s in signals],
        "monthly": {d.strftime("%Y-%m"): clean(v) for d, v in monthly.items()},
        "equity": {"dates": [d.strftime("%Y-%m-%d") for d in eq.index],
                   "series": {n: [round(v, 2) for v in eq[n]] for n in names}},
    }
    if not args.no_top50:
        import top50
        print("\nТоп 50 компании...")
        results["top50"] = top50.run(market, args.synthetic, args.refresh, args.model)

    def deep(v):
        if isinstance(v, dict):
            return {k: deep(x) for k, x in v.items()}
        if isinstance(v, list):
            return [deep(x) for x in v]
        return clean(v)

    with open(os.path.join(config.REPORT_DIR, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(deep(results), fh, ensure_ascii=False, indent=1)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 5))
        for n in names:
            (1 + port[n]).cumprod().mul(100).plot(ax=ax, label=n, lw=2 if n == main_name else 1.2)
        ax.set_title("Растеж на 100 € (out-of-sample)")
        ax.set_ylabel("€")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(config.REPORT_DIR, "equity_curve.png"), dpi=120)
        print(f"\nГрафика: {config.REPORT_DIR}/equity_curve.png")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
