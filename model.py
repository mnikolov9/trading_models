"""Модели и walk-forward обучение (само минало -> прогноза за бъдещето)."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

try:
    from lightgbm import LGBMClassifier
    HAS_LGBM = True
except ImportError:  # резервен вариант със същата идея (gradient boosting)
    from sklearn.ensemble import HistGradientBoostingClassifier
    HAS_LGBM = False


def make_model(kind: str = "gbm", seed: int = 0):
    if kind == "logreg":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             LogisticRegression(C=0.1, max_iter=1000))
    if HAS_LGBM:
        return LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=15,
                              min_child_samples=50, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.7, reg_lambda=1.0, random_state=seed, verbose=-1)
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.03, max_leaf_nodes=15,
                                          min_samples_leaf=50, l2_regularization=1.0, random_state=seed)


def walk_forward(X: pd.DataFrame, fwd_ret: pd.Series, horizon: int, min_train: int,
                 retrain_every: int, kind: str = "gbm") -> pd.Series:
    """Връща out-of-sample вероятност за ръст за всеки ден след началния период.

    На ден i обучаваме само върху редове j, чиято цел вече е известна: j + horizon <= i
    (embargo = horizon), за да няма изтичане на бъдеща информация.
    """
    y = (fwd_ret > 0).astype(int)
    valid_x = X.notna().mean(axis=1) > 0.8
    probs = pd.Series(np.nan, index=X.index)
    n = len(X)

    for start in range(min_train, n, retrain_every):
        train_end = start - horizon                       # изключително
        tr = np.arange(train_end)
        tr = tr[valid_x.values[tr] & fwd_ret.notna().values[tr]]
        if len(tr) < 250:
            continue
        model = make_model(kind)
        Xtr = X.iloc[tr]
        if kind != "logreg" and not HAS_LGBM:
            Xtr = Xtr.fillna(Xtr.median())
        model.fit(Xtr, y.iloc[tr])

        te = np.arange(start, min(start + retrain_every, n))
        Xte = X.iloc[te]
        if kind != "logreg" and not HAS_LGBM:
            Xte = Xte.fillna(Xtr.median())
        probs.iloc[te] = model.predict_proba(Xte)[:, 1]
    return probs
