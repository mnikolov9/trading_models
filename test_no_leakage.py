"""Тест за изтичане на бъдеща информация.

При чиста случайна разходка никой модел не може да предвиди посоката.
Ако точността излезе значимо над 50%, в кода има грешка (lookahead).
"""
import numpy as np

import config
import data
import features
import model as mdl


def test_random_walk(n_seeds: int = 3):
    accs = []
    for seed in range(n_seeds):
        df = data.synthetic("RW", n_days=2500, seed=100 + seed, signal=0.0, drift=0.0)
        X = features.build_features(df)
        fwd = features.build_target(df, config.HORIZON)
        p = mdl.walk_forward(X, fwd, config.HORIZON, config.MIN_TRAIN_DAYS, 63)
        m = p.notna() & fwd.notna()
        accs.append(((p[m] > 0.5) == (fwd[m] > 0)).mean())
    acc = float(np.mean(accs))
    print(f"Случайна разходка: средна точност {acc:.1%} (очаквано ~50%)")
    assert 0.46 < acc < 0.54, "Подозрение за изтичане на бъдеща информация!"


def test_features_use_only_past():
    """Промяна на бъдещите цени не трябва да променя признаците за миналите дни."""
    df = data.synthetic("X", n_days=800, seed=7)
    f1 = features.build_features(df)
    df2 = df.copy()
    df2.iloc[600:] *= 1.5
    f2 = features.build_features(df2)
    diff = (f1.iloc[:600] - f2.iloc[:600]).abs().max().max()
    print(f"Макс. разлика в признаците преди промяната: {diff}")
    assert diff < 1e-9


if __name__ == "__main__":
    test_features_use_only_past()
    test_random_walk()
    print("OK: няма изтичане на бъдеща информация")
