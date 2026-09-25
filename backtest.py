"""Backtest: превръща вероятностите в позиции и смята доходност с разходи."""
import numpy as np
import pandas as pd


def periods_per_year(index: pd.DatetimeIndex) -> int:
    """252 за акции (само делнични дни), 365 за крипто (търгува се и в събота/неделя)."""
    return 365 if (index.dayofweek >= 5).mean() > 0.1 else 252


def positions_from_probs(probs: pd.Series, close: pd.Series, strategy: dict, max_lev: float = 1.0) -> pd.Series:
    """Позиция (дял от капитала) за всеки ден според стратегията и вероятността за ръст."""
    ppy = periods_per_year(close.index)
    vol = close.pct_change().rolling(21).std() * np.sqrt(ppy)
    size = (strategy["target_vol"] / vol).clip(upper=max_lev)

    mode = strategy["mode"]
    if mode == "timing":
        direction = (probs > strategy["prob_long"]).astype(float)
    elif mode == "filter":
        direction = (probs >= strategy["prob_exit"]).astype(float)
    elif mode == "always":
        direction = pd.Series(1.0, index=probs.index)
    else:
        raise ValueError(f"Непознат mode: {mode}")
    direction[probs.isna()] = np.nan   # само out-of-sample периода
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


def hit_rate(probs: pd.Series, fwd_ret: pd.Series) -> tuple[float, float]:
    """(точност на модела, базова точност ако винаги казваш "нагоре")."""
    m = probs.notna() & fwd_ret.notna()
    up = fwd_ret[m] > 0
    return ((probs[m] > 0.5) == up).mean(), up.mean()


def portfolio(returns: dict) -> pd.Series:
    """Равни тегла между активите, които вече се търгуват (преди старта си актив не участва).
    Дни без търговия за даден актив (напр. уикенд за акции) = 0% за него."""
    df = pd.DataFrame(returns).sort_index()
    for c in df:
        first = df[c].first_valid_index()
        df.loc[first:, c] = df.loc[first:, c].fillna(0.0)
    return df.mean(axis=1, skipna=True).dropna()
