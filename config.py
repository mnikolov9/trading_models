"""Настройки на проекта."""

# Активи: тикер в Yahoo Finance -> кратко име
ASSETS = {
    "SPY": "S&P 500",
    "GLD": "Злато",
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
}

# Пазарен индекс за cross-asset признаци
MARKET_TICKER = "SPY"

START_DATE = "2015-01-01"
DATA_DIR = "data"
REPORT_DIR = "reports"

# Прогнозен хоризонт (в търговски дни): предвиждаме посоката след HORIZON дни
HORIZON = 5

# Walk-forward
MIN_TRAIN_DAYS = 750      # ~3 години история преди първата прогноза
RETRAIN_EVERY = 21        # преобучение всеки ~месец

# Правила за търговия
PROB_LONG = 0.53          # купуваме само ако вероятност за ръст > прага
ALLOW_SHORT = False       # за начало само long / cash
TARGET_VOL = 0.15         # целева годишна волатилност на всеки актив (volatility targeting)
MAX_LEVERAGE = 1.0        # без ливъридж

# Разходи: комисионна + спред за една посока, в базисни точки (1 bp = 0.01%)
COST_BPS = {"SPY": 3, "GLD": 5, "BTC-USD": 15, "ETH-USD": 15}

# Целева доходност, срещу която сравняваме
TARGET_ANNUAL_RETURN = (0.15, 0.20)
