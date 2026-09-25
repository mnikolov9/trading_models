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
    args = ap.parse_args()

    os.makedirs(config.REPORT_DIR, exist_ok=True)
    prices = load(args.synthetic, args.refresh)
    market = prices.get(config.MARKET_TICKER)

    rows, strat_rets, bh_rets, signals = [], {}, {}, []
    print(f"Модел: {args.model} ({'LightGBM' if mdl.HAS_LGBM else 'sklearn HistGradientBoosting'})"
          if args.model == "gbm" else "Модел: logistic regression")

    for t, df in prices.items():
        mkt = None if t == config.MARKET_TICKER else market
        X = features.build_features(df, mkt)
        fwd = features.build_target(df, config.HORIZON)
        probs = mdl.walk_forward(X, fwd, config.HORIZON, config.MIN_TRAIN_DAYS,
                                 config.RETRAIN_EVERY, args.model)
        oos = probs.first_valid_index()
        pos = bt.positions_from_probs(probs, df["close"], config.PROB_LONG, config.ALLOW_SHORT,
                                      config.TARGET_VOL, config.MAX_LEVERAGE)
        cost = config.COST_BPS.get(t, 10)
        sr = bt.run(pos, df["close"], cost).loc[oos:]
        bh = df["close"].pct_change().loc[oos:].fillna(0.0)
        strat_rets[t], bh_rets[t] = sr, bh

        m, mb = bt.metrics(sr), bt.metrics(bh)
        rows.append({"Актив": config.ASSETS[t], "Стратегия": "Модел", **m,
                     "Точност (посока)": bt.hit_rate(probs, fwd), "В пазара": (pos.loc[oos:] > 0).mean()})
        rows.append({"Актив": config.ASSETS[t], "Стратегия": "Купи и дръж", **mb})
        signals.append({"Актив": config.ASSETS[t], "Дата": df.index[-1].date(),
                        "Вероятност за ръст": probs.iloc[-1], "Позиция (дял от капитала)": pos.iloc[-1]})

    # Портфейл: равни тегла между активите, общ календар
    def portfolio(d):
        return pd.DataFrame(d).fillna(0.0).mean(axis=1)

    p_strat, p_bh = portfolio(strat_rets), portfolio(bh_rets)
    rows.append({"Актив": "ПОРТФЕЙЛ", "Стратегия": "Модел", **bt.metrics(p_strat, 252)})
    rows.append({"Актив": "ПОРТФЕЙЛ", "Стратегия": "Купи и дръж", **bt.metrics(p_bh, 252)})

    report = pd.DataFrame(rows)
    report.to_csv(os.path.join(config.REPORT_DIR, "summary.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(signals).to_csv(os.path.join(config.REPORT_DIR, "latest_signals.csv"), index=False, encoding="utf-8-sig")
    monthly = (1 + p_strat).resample("ME").prod() - 1
    monthly.to_frame("Портфейл (модел)").to_csv(os.path.join(config.REPORT_DIR, "monthly_returns.csv"), encoding="utf-8-sig")

    pct = ["Годишна доходност", "Средно на месец", "Волатилност", "Макс. спад", "Печеливши месеци",
           "Най-лош месец", "Точност (посока)", "В пазара"]
    show = report.copy()
    for col in pct:
        show[col] = show[col].map(lambda v: "" if pd.isna(v) else f"{v:.1%}")
    show["Sharpe"] = show["Sharpe"].map(lambda v: f"{v:.2f}")
    show["Години"] = show["Години"].map(lambda v: f"{v:.1f}")
    pd.set_option("display.width", 250, "display.max_columns", 20)
    print("\n" + show.to_string(index=False))

    cagr = bt.metrics(p_strat, 252)["Годишна доходност"]
    lo, hi = config.TARGET_ANNUAL_RETURN
    verdict = "в целта" if lo <= cagr <= hi else ("над целта (провери за грешки!)" if cagr > hi else "под целта")
    print(f"\nПортфейл: {cagr:.1%} годишно -> {verdict} ({lo:.0%}-{hi:.0%})")
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

    eq_s, eq_b = (1 + p_strat).cumprod() * 100, (1 + p_bh).cumprod() * 100
    eq_w = pd.DataFrame({"model": eq_s, "bh": eq_b}).resample("W").last().dropna()
    results = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "synthetic": args.synthetic,
        "model": ("LightGBM" if mdl.HAS_LGBM else "HistGradientBoosting") if args.model == "gbm" else "Logistic regression",
        "horizon": config.HORIZON,
        "prob_long": config.PROB_LONG,
        "target": list(config.TARGET_ANNUAL_RETURN),
        "summary": [{k: clean(v) for k, v in r.items()} for r in rows],
        "signals": [{k: clean(v) for k, v in s.items()} for s in signals],
        "monthly": {d.strftime("%Y-%m"): clean(v) for d, v in monthly.items()},
        "equity": {"dates": [d.strftime("%Y-%m-%d") for d in eq_w.index],
                   "model": [round(v, 2) for v in eq_w["model"]],
                   "bh": [round(v, 2) for v in eq_w["bh"]]},
    }
    with open(os.path.join(config.REPORT_DIR, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 5))
        (1 + p_strat).cumprod().mul(100).plot(ax=ax, label="Модел (портфейл)", color="#2563eb", lw=2)
        (1 + p_bh).cumprod().mul(100).plot(ax=ax, label="Купи и дръж (портфейл)", color="#9ca3af", lw=1.5)
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
