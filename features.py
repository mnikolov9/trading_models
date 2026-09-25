"""Признаци (features) и целева променлива.

Правило: всеки признак за ден t използва САМО информация до затварянето на ден t.
Целта е доходността от t до t+HORIZON, т.е. изцяло в бъдещето.
"""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def build_features(df: pd.DataFrame, market: pd.DataFrame | None = None, macro: dict | None = None) -> pd.DataFrame:
    c = df["close"]
    r = np.log(c).diff()
    f = pd.DataFrame(index=df.index)

    # Доходности и моментум
    for n in (1, 2, 5, 10, 21, 63, 126):
        f[f"ret_{n}"] = np.log(c / c.shift(n))

    # Волатилност
    for n in (5, 21, 63):
        f[f"vol_{n}"] = r.rolling(n).std()
    f["vol_ratio"] = f["vol_5"] / f["vol_63"]
    hl = np.log(df["high"] / df["low"])
    f["range_21"] = hl.rolling(21).mean()

    # Нормализиран моментум (доходност / волатилност)
    f["mom_21_z"] = f["ret_21"] / (f["vol_21"] * np.sqrt(21))
    f["mom_63_z"] = f["ret_63"] / (f["vol_63"] * np.sqrt(63))

    # Разстояние до пълзящи средни
    for n in (20, 50, 200):
        f[f"dist_ma{n}"] = c / c.rolling(n).mean() - 1

    # Осцилатори
    f["rsi_14"] = rsi(c, 14)
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    f["macd_hist"] = (macd - macd.ewm(span=9, adjust=False).mean()) / c

    # Позиция спрямо max/min
    f["pos_252"] = (c - c.rolling(252).min()) / (c.rolling(252).max() - c.rolling(252).min())
    f["drawdown_252"] = c / c.rolling(252).max() - 1

    # Обем
    lv = np.log(df["volume"].replace(0, np.nan))
    f["volume_z"] = (lv - lv.rolling(63).mean()) / lv.rolling(63).std()

    # Календар
    f["dow"] = df.index.dayofweek
    f["month"] = df.index.month

    # Cross-asset: състояние на широкия пазар
    if market is not None:
        mc = market["close"].reindex(df.index).ffill()
        mr = np.log(mc).diff()
        f["mkt_ret_5"] = np.log(mc / mc.shift(5))
        f["mkt_ret_21"] = np.log(mc / mc.shift(21))
        f["mkt_vol_21"] = mr.rolling(21).std()
        f["mkt_dist_ma200"] = mc / mc.rolling(200).mean() - 1
        f["corr_mkt_63"] = r.rolling(63).corr(mr)

    # Макро: страх (VIX), лихви (10г. САЩ), долар (DXY)
    for name, series in (macro or {}).items():
        m = series.reindex(df.index, method="ffill")
        f[f"{name}_z"] = (m - m.rolling(252).mean()) / m.rolling(252).std()
        f[f"{name}_chg_5"] = m / m.shift(5) - 1
        f[f"{name}_chg_21"] = m / m.shift(21) - 1

    return f.replace([np.inf, -np.inf], np.nan)


def build_target(df: pd.DataFrame, horizon: int) -> pd.Series:
    """Бъдеща лог-доходност за следващите `horizon` бара (НЕ се ползва като признак)."""
    c = df["close"]
    return np.log(c.shift(-horizon) / c)
