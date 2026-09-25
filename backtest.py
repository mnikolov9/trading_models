"""Backtest: превръща вероятностите в позиции и смята доходност с разходи."""
import numpy as np
import pandas as pd


def periods_per_year(index: pd.DatetimeIndex) -> int:
    """252 за акции (само делнични дни), 365 за крипто (търгува се и в събота/неделя)."""
    return 365 if (index.dayofweek >= 5).mean() > 0.1 else 252


def positions_from_probs(probs: pd.Series, close: pd.Series, prob_long: float, allow_short: bool,
                         target_vol: float, max_lev: float) -> pd.Series:
    ppy = periods_per_year(close.index)
    ret = close.pct_change()
    vol = ret.rolling(21).std() * np.sqrt(ppy)
    size = (target_vol / vol).clip(upper=max_lev)

    direction = pd.Series(0.0, index=probs.index)
    direction[probs > prob_long] = 1.0
    if allow_short:
        direction[probs < 1 - prob_long] = -1.0
    direction[probs.isna()] = np.nan
    return (direction * size).fillna(0.0)


def run(pos: pd.Series, close: pd.Series, cost_bps: float) -> pd.Series:
    """Позицията, решена при затваряне на ден t, носи доходността на ден t+1."""
    ret = close.pct_change().fillna(0.0)
    held = pos.shift(1).fillna(0.0)
    turnover = pos.diff().abs().fillna(pos.abs())
    cost = (turnover * cost_bps / 1e4).shift(1).fillna(0.0)
    return held * ret - cost


def metrics(r: pd.Series, ppy: int | None = None) -> dict:
    r = r.dropna()
    if len(r) < 2:
        return {}
    ppy = ppy or periods_per_year(r.index)
    eq = (1 + r).cumprod()
    years = len(r) / ppy
    cagr = eq.iloc[-1] ** (1 / years) - 1
    vol = r.std() * np.sqrt(ppy)
    sharpe = r.mean() / r.std() * np.sqrt(ppy) if r.std() > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    monthly = (1 + r).resample("ME").prod() - 1
    return {
        "Годишна доходност": cagr,
        "Средно на месец": (1 + cagr) ** (1 / 12) - 1,
        "Волатилност": vol,
        "Sharpe": sharpe,
        "Макс. спад": dd,
        "Печеливши месеци": (monthly > 0).mean(),
        "Най-лош месец": monthly.min(),
        "Години": years,
    }


def hit_rate(probs: pd.Series, fwd_ret: pd.Series) -> float:
    m = probs.notna() & fwd_ret.notna()
    return ((probs[m] > 0.5) == (fwd_ret[m] > 0)).mean()
