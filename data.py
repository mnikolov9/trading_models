"""Зареждане на пазарни данни (Yahoo Finance) с локален кеш в CSV."""
import os
import numpy as np
import pandas as pd

import config


def _cache_path(ticker: str) -> str:
    return os.path.join(config.DATA_DIR, f"{ticker.replace('^', '')}.csv")


def download(ticker: str, start: str = config.START_DATE, refresh: bool = False) -> pd.DataFrame:
    """Връща DataFrame с колони open, high, low, close, volume и DatetimeIndex."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    path = _cache_path(ticker)
    if os.path.exists(path) and not refresh:
        return pd.read_csv(path, index_col=0, parse_dates=True)

    import yfinance as yf  # импорт тук, за да работят тестовете и без него

    import time

    df = pd.DataFrame()
    for attempt in range(4):  # Yahoo понякога ограничава заявките -> повторни опити
        try:
            df = yf.download(ticker, start=start, auto_adjust=True, progress=False, threads=False)
        except Exception as exc:  # noqa: BLE001
            print(f"{ticker}: опит {attempt + 1} неуспешен ({exc})")
        if not df.empty:
            break
        time.sleep(10 * (attempt + 1))
    if df.empty:
        if os.path.exists(path):  # стар кеш е по-добре от нищо
            print(f"{ticker}: ползвам стари данни от кеша")
            return pd.read_csv(path, index_col=0, parse_dates=True)
        raise RuntimeError(f"Няма данни за {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.dropna()
    df.to_csv(path)
    return df


def load_all(tickers=None, refresh: bool = False) -> dict:
    tickers = tickers or list(config.ASSETS)
    return {t: download(t, refresh=refresh) for t in tickers}


def synthetic(ticker: str, n_days: int = 2500, seed: int = 0, drift: float = 0.0003,
              vol: float = 0.012, weekdays_only: bool = True, signal: float = 0.0) -> pd.DataFrame:
    """Изкуствени данни за тестове.

    signal=0 -> чиста случайна разходка (моделът НЕ трябва да печели систематично).
    signal>0 -> вграден слаб моментум, който моделът трябва да открие.
    """
    rng = np.random.default_rng(seed)
    freq = "B" if weekdays_only else "D"
    idx = pd.date_range("2015-01-01", periods=n_days, freq=freq)
    eps = rng.normal(0, vol, n_days)
    r = np.zeros(n_days)
    for i in range(n_days):
        mom = r[max(0, i - 10):i].mean() if i > 0 else 0.0
        r[i] = drift + signal * np.sign(mom) * vol + eps[i]
    close = 100 * np.exp(np.cumsum(r))
    open_ = close * np.exp(rng.normal(0, vol / 4, n_days))
    high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, vol / 3, n_days)))
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, vol / 3, n_days)))
    volume = rng.lognormal(15, 0.3, n_days)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)
