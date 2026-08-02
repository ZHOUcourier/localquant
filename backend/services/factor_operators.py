"""因子算子库 — 复刻 PandaAI「公式版」量化算子

设计：所有算子作用于「面板 DataFrame」(index=日期, columns=股票代码)。
- 截面算子（RANK/SCALE/ZSCORE）按行(axis=1，同一天所有股票)计算；
- 时序算子（DELAY/DELTA/MA/SUM/STD/TS_*/DECAYLINEAR...）按列(axis=0，单只股票时间序列)计算；
- 双面板算子（CORR/COV）按列做滚动配对计算。

对齐官网《PandaAI 因子编写与函数参考手册》(community/article/72)。
调用时直接用函数名（无需类名前缀），大小写均可（同时注册大写与小写别名）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _as_int(n) -> int:
    return int(n)


# ── 直接逐元素算子 ────────────────────────────────────────────


def ABS(x):
    return x.abs() if isinstance(x, (pd.DataFrame, pd.Series)) else np.abs(x)


def LOG(x):
    return np.log(x)


def LOGABS(x):
    return np.log(ABS(x))


def SIGN(x):
    return np.sign(x)


def SIGNEDPOWER(x, n):
    return np.sign(x) * (ABS(x) ** n)


def POWER(x, n):
    return x**n


def AS_FLOAT(x):
    return x.astype(float) if hasattr(x, "astype") else float(x)


def RD(x, n=2):
    return np.round(x, _as_int(n))


def SIN(x):
    return np.sin(x)


def COS(x):
    return np.cos(x)


def TAN(x):
    return np.tan(x)


def ARCSIN(x):
    return np.arcsin(x)


def ARCCOS(x):
    return np.arccos(x)


def ARCTAN(x):
    return np.arctan(x)


# ── 截面算子（按行 axis=1）────────────────────────────────────


def RANK(x):
    """截面排序分位数 [0,1]"""
    return x.rank(axis=1, pct=True)


def SCALE(x, a=1):
    """按截面缩放，使每行绝对值之和为 a"""
    denom = x.abs().sum(axis=1).replace(0, np.nan)
    return x.div(denom, axis=0) * a


def ZSCORE(x):
    """截面 z-score 标准化"""
    mean = x.mean(axis=1)
    std = x.std(axis=1).replace(0, np.nan)
    return x.sub(mean, axis=0).div(std, axis=0)


def INDUSTRY_NEUTRALIZE(x, industry_map=None):
    """行业中性化：逐日截面在行业内去均值（剔离行业暴露）

    industry_map: {code: industry} 行业分类映射；为空时从求值命名空间注入的
    _INDUSTRY_MAP 取（由 build_operator_namespace 填入）。无行业数据时显式报错，
    不再静默退化为全市场去均值（去均值请直接用 ZSCORE/减均值）。
    """
    if industry_map is None:
        industry_map = globals().get("_ACTIVE_INDUSTRY_MAP")
    if not industry_map:
        raise ValueError(
            "INDUSTRY_NEUTRALIZE 需要行业分类数据 — 请先在「数据管理」页下载数据以采集行业快照"
        )
    industry = pd.Series(industry_map)
    # 仅保留有行业归属且在因子列中的股票
    cols = [c for c in x.columns if c in industry.index]
    if not cols:
        raise ValueError("INDUSTRY_NEUTRALIZE：因子股票与行业分类无交集")
    sub = x[cols]
    groups = industry.reindex(cols)
    # 按行业分组做截面去均值（对每个日期/行业）
    demeaned = sub.sub(sub.T.groupby(groups).transform("mean").T)
    result = x.copy()
    result[cols] = demeaned
    return result


# ── 时序算子（按列 axis=0）────────────────────────────────────


def DELAY(x, n):
    return x.shift(_as_int(n))


REF = DELAY


def DELTA(x, n=1):
    return x - x.shift(_as_int(n))


DIFF = DELTA


def MA(x, n):
    return x.rolling(_as_int(n), min_periods=1).mean()


def SUM(x, n):
    return x.rolling(_as_int(n), min_periods=1).sum()


def SUMAC(x, n):
    """过去 N 期累计求和（同 SUM）"""
    return SUM(x, n)


def PRODUCT(x, n):
    return x.rolling(_as_int(n), min_periods=1).apply(np.prod, raw=True)


def STD(x, n):
    return x.rolling(_as_int(n), min_periods=2).std()


STDDEV = STD


def VAR(x, n):
    return x.rolling(_as_int(n), min_periods=2).var()


def TS_MAX(x, n):
    return x.rolling(_as_int(n), min_periods=1).max()


def TS_MIN(x, n):
    return x.rolling(_as_int(n), min_periods=1).min()


HHV = TS_MAX
LLV = TS_MIN


def TS_RANK(x, n):
    """过去 N 日的时序排名分位数"""
    n = _as_int(n)
    return x.rolling(n, min_periods=1).apply(
        lambda s: pd.Series(s).rank(pct=True).iloc[-1], raw=False
    )


def TS_ARGMAX(x, n):
    n = _as_int(n)
    return x.rolling(n, min_periods=1).apply(lambda s: int(np.argmax(s)), raw=True)


def TS_ARGMIN(x, n):
    n = _as_int(n)
    return x.rolling(n, min_periods=1).apply(lambda s: int(np.argmin(s)), raw=True)


def HIGHDAY(x, n):
    """过去 N 期最高值距今期数"""
    n = _as_int(n)
    return x.rolling(n, min_periods=1).apply(
        lambda s: n - 1 - int(np.argmax(s)), raw=True
    )


def LOWDAY(x, n):
    n = _as_int(n)
    return x.rolling(n, min_periods=1).apply(
        lambda s: n - 1 - int(np.argmin(s)), raw=True
    )


HHVBARS = HIGHDAY
LLVBARS = LOWDAY


def TS_MIDDLE(x, n):
    """过去 N 日最大最小值的均值"""
    return (TS_MAX(x, n) + TS_MIN(x, n)) / 2


def TS_MEDIAN(x, n):
    return x.rolling(_as_int(n), min_periods=1).median()


def TS_MAD(x, n):
    """过去 N 日平均绝对偏差"""
    return x.rolling(_as_int(n), min_periods=1).apply(
        lambda s: np.mean(np.abs(s - np.mean(s))), raw=True
    )


AVEDEV = TS_MAD


def TS_ZSCORE(x, n):
    """滚动 z-score"""
    n = _as_int(n)
    mean = x.rolling(n, min_periods=2).mean()
    std = x.rolling(n, min_periods=2).std()
    return (x - mean) / std.replace(0, np.nan)


def TS_SKEW(x, n):
    return x.rolling(_as_int(n), min_periods=3).skew()


def TS_KURT(x, n):
    return x.rolling(_as_int(n), min_periods=4).kurt()


def DECAYLINEAR(x, n):
    """线性衰减加权移动平均（权重 n, n-1, ..., 1）"""
    n = _as_int(n)
    weights = np.arange(1, n + 1, dtype=float)
    weights /= weights.sum()

    def _wavg(s):
        if len(s) < n:
            w = np.arange(1, len(s) + 1, dtype=float)
            w /= w.sum()
            return np.dot(s, w)
        return np.dot(s, weights)

    return x.rolling(n, min_periods=1).apply(_wavg, raw=True)


DECAY_LINEAR = DECAYLINEAR


def EMA(x, n):
    return x.ewm(span=_as_int(n), adjust=False).mean()


def WMA(x, n):
    """加权移动平均（权重 1..n，近端权重大）"""
    n = _as_int(n)
    weights = np.arange(1, n + 1, dtype=float)
    weights /= weights.sum()
    return x.rolling(n, min_periods=1).apply(
        lambda s: np.dot(s, weights) if len(s) == n else np.mean(s), raw=True
    )


def SMA(x, n, m=1):
    """中式 SMA：Y = (m*X + (n-m)*Y_prev) / n，用 ewm 近似（alpha=m/n）"""
    n, m = _as_int(n), _as_int(m)
    alpha = m / n if n else 0.5
    return x.ewm(alpha=alpha, adjust=False).mean()


def RETURNS(x, n=1):
    return x.pct_change(_as_int(n))


ROC = RETURNS
PCT_CHANGE = RETURNS


def COUNT(cond, n):
    """过去 N 日满足条件的次数"""
    return cond.astype(float).rolling(_as_int(n), min_periods=1).sum()


def EVERY(cond, n):
    """过去 N 日是否全部为 True（1/0）"""
    return cond.astype(float).rolling(_as_int(n), min_periods=1).min()


def EXIST(cond, n):
    """过去 N 日是否至少一次为 True（1/0）"""
    return cond.astype(float).rolling(_as_int(n), min_periods=1).max()


def BARSSINCEN(cond, n):
    """过去 N 日内第一次 True 距今期数（窗口内无 True 为 NaN）"""
    return (
        cond.astype(float)
        .rolling(_as_int(n), min_periods=1)
        .apply(
            lambda s: len(s) - 1 - int(np.argmax(s)) if s.any() else np.nan, raw=True
        )
    )


def CONST(x):
    """用最后一个值填充整个序列"""
    return x * 0 + x.ffill().iloc[-1]


def BARSLAST(cond):
    """距上一次条件为 True 已过去的期数"""
    cond = cond.astype(bool)
    pos = np.arange(len(cond), dtype=float)
    if isinstance(cond, pd.Series):
        marked = pd.Series(np.where(cond.to_numpy(), pos, np.nan), index=cond.index)
        return pd.Series(pos, index=cond.index) - marked.ffill()
    marked = pd.DataFrame(
        np.where(cond.to_numpy(), pos[:, None], np.nan),
        index=cond.index,
        columns=cond.columns,
    )
    base = pd.DataFrame(
        np.tile(pos[:, None], (1, cond.shape[1])),
        index=cond.index,
        columns=cond.columns,
    )
    return base - marked.ffill()


def BARSLASTCOUNT(cond):
    """连续满足条件的周期数"""
    s = cond.astype(float)
    cum = s.cumsum()
    return (cum - cum.mask(s > 0).ffill().fillna(0)) * (s > 0)


def SLOPE(x, n):
    """过去 N 期线性回归斜率"""
    n = _as_int(n)
    return x.rolling(n, min_periods=2).apply(
        lambda s: np.polyfit(np.arange(len(s)), s, 1)[0], raw=True
    )


def ANGLE(x, n):
    """过去 N 期线性回归线角度（度）"""
    return np.degrees(np.arctan(SLOPE(x, n)))


def INTERCEPT(x, n):
    """过去 N 期线性回归截距"""
    n = _as_int(n)
    return x.rolling(n, min_periods=2).apply(
        lambda s: np.polyfit(np.arange(len(s)), s, 1)[1], raw=True
    )


def FORCAST(x, n):
    """N 周期线性回归的当期预测值"""
    n = _as_int(n)
    return x.rolling(n, min_periods=2).apply(
        lambda s: np.polyval(np.polyfit(np.arange(len(s)), s, 1), len(s) - 1), raw=True
    )


def DMA(x, a=0.1):
    """动态移动平均（A 为平滑因子，0<A<1）"""
    return x.ewm(alpha=float(a), adjust=False).mean()


def FUTURE_RETURNS(x, n=1):
    """相对于 N 日后的变化百分比（含未来信息，仅用于研究标签）"""
    n = _as_int(n)
    return x.shift(-n) / x - 1


def SHARPE(x, n):
    """过去 N 日收益率均值 / 标准差"""
    n = _as_int(n)
    r = x.pct_change()
    return r.rolling(n, min_periods=2).mean() / r.rolling(n, min_periods=2).std()


def SUM_ABS_PRICE_CHANGE(x, n):
    """N 日内价格变化绝对值总和"""
    return x.diff().abs().rolling(_as_int(n), min_periods=1).sum()


def MEAN_ABS_PRICE_CHANGE(x, n):
    """N 日内价格变化绝对值平均"""
    return x.diff().abs().rolling(_as_int(n), min_periods=1).mean()


# ── 双序列逐元素算子 ─────────────────────────────────────────


def MAX(a, b):
    if isinstance(a, (pd.DataFrame, pd.Series)) or isinstance(
        b, (pd.DataFrame, pd.Series)
    ):
        return np.maximum(a, b)
    return max(a, b)


def MIN(a, b):
    if isinstance(a, (pd.DataFrame, pd.Series)) or isinstance(
        b, (pd.DataFrame, pd.Series)
    ):
        return np.minimum(a, b)
    return min(a, b)


def MEAN(a, b):
    """MEAN(A,B)：若 B 为整数则视为时序均值 MA(A,B)（兼容 Alpha191 mean(x,n)），否则逐元素均值"""
    if isinstance(b, (int, float)) and not isinstance(b, bool):
        return MA(a, int(b))
    return (a + b) / 2


def IF(cond, a, b):
    return (
        cond * 0 + np.where(cond, a, b)
        if isinstance(cond, (pd.DataFrame, pd.Series))
        else (a if cond else b)
    )


def EQUAL(a, b):
    """逐元素相等判断（1/0）"""
    return (a == b).astype(float) if hasattr(a, "astype") else float(a == b)


def VALUEWHEN(cond, b):
    """条件为 True 时取 B 的当前值，否则沿用上一次取值"""
    return b.where(cond.astype(bool)).ffill()


def CROSS(x, y):
    """X 是否从下向上穿过 Y（金叉判断，1/0）"""
    y_prev = y.shift(1) if isinstance(y, (pd.DataFrame, pd.Series)) else y
    return ((x > y) & (x.shift(1) <= y_prev)).astype(float)


def LONGCROSS(a, b, n):
    """A 连续 N 期低于 B 后是否上穿 B（1/0）"""
    below = (a < b).astype(float)
    return CROSS(a, b) * below.shift(1).rolling(_as_int(n), min_periods=1).min()


def LAST(x, n, m):
    """X 从前 N 期到前 M 期是否全为 True（N≥M，1/0）"""
    n, m = _as_int(n), _as_int(m)
    span = max(n - m + 1, 1)
    return x.astype(float).shift(m).rolling(span, min_periods=1).min()


# ── 双面板滚动算子 ───────────────────────────────────────────


def CORR(a, b, n):
    """按列的滚动相关系数"""
    n = _as_int(n)
    return a.rolling(n, min_periods=2).corr(b)


CORRELATION = CORR


def COV(a, b, n):
    n = _as_int(n)
    return a.rolling(n, min_periods=2).cov(b)


COVARIANCE = COV


def SUMIF(a, b, n):
    """条件求和：a 为 True 时累加 b，取过去 N 日之和"""
    masked = b.where(a.astype(bool), 0)
    return SUM(masked, n)


def REGBETA(a, b, n):
    """滚动回归斜率 beta = cov(a,b)/var(b)"""
    return COV(a, b, n) / VAR(b, n)


def REGRESI(a, b, n):
    """滚动回归残差近似：a - beta*b"""
    beta = REGBETA(a, b, n)
    return a - beta * b


TS_REGRESSION = REGBETA


# ── 技术指标（常用）──────────────────────────────────────────


def ADV(volume, n):
    """N 日平均成交量"""
    return MA(volume, n)


def RSI(x, n):
    delta = x.diff()
    up = delta.clip(lower=0).rolling(_as_int(n), min_periods=1).mean()
    down = (-delta.clip(upper=0)).rolling(_as_int(n), min_periods=1).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


# ── 复合技术指标（对齐官网函数手册，逐列作用于面板） ──────────────


def MACD_DIF(close, short=12, long=26, m=9):
    return EMA(close, short) - EMA(close, long)


def MACD_DEA(close, short=12, long=26, m=9):
    return EMA(MACD_DIF(close, short, long, m), m)


def MACD(close, short=12, long=26, m=9):
    return (MACD_DIF(close, short, long, m) - MACD_DEA(close, short, long, m)) * 2


def BOLL_MID(close, n=20, p=2):
    return MA(close, n)


def BOLL_UPPER(close, n=20, p=2):
    return MA(close, n) + p * STD(close, n)


def BOLL_LOWER(close, n=20, p=2):
    return MA(close, n) - p * STD(close, n)


def ATR(high, low, close, n=14):
    prev_close = close.shift(1)
    tr = np.maximum(
        high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs())
    )
    return tr.rolling(_as_int(n), min_periods=1).mean()


def CCI(high, low, close, n=14):
    tp = (high + low + close) / 3
    ma = tp.rolling(_as_int(n), min_periods=1).mean()
    md = (tp - ma).abs().rolling(_as_int(n), min_periods=1).mean()
    return (tp - ma) / (0.015 * md.replace(0, np.nan))


def WR(close, high, low, n=14):
    hh = high.rolling(_as_int(n), min_periods=1).max()
    ll = low.rolling(_as_int(n), min_periods=1).min()
    return (hh - close) / (hh - ll).replace(0, np.nan) * 100


def BIAS(close, n=6):
    ma = MA(close, n)
    return (close - ma) / ma.replace(0, np.nan) * 100


def KDJ_K(close, high, low, n=9, m1=3, m2=3):
    ll = low.rolling(_as_int(n), min_periods=1).min()
    hh = high.rolling(_as_int(n), min_periods=1).max()
    rsv = (close - ll) / (hh - ll).replace(0, np.nan) * 100
    return rsv.ewm(alpha=1 / _as_int(m1), adjust=False).mean()


def KDJ_D(close, high, low, n=9, m1=3, m2=3):
    return (
        KDJ_K(close, high, low, n, m1, m2)
        .ewm(alpha=1 / _as_int(m2), adjust=False)
        .mean()
    )


def KDJ_J(close, high, low, n=9, m1=3, m2=3):
    k = KDJ_K(close, high, low, n, m1, m2)
    d = KDJ_D(close, high, low, n, m1, m2)
    return 3 * k - 2 * d


def OBV(close, volume):
    sign = np.sign(close.diff()).fillna(0)
    return (sign * volume).cumsum()


def BOLL_WIDTH(close, n=20):
    """布林带宽度：上轨 - 下轨"""
    return BOLL_UPPER(close, n, 2) - BOLL_LOWER(close, n, 2)


def PSY(close, n=12):
    """心理线：上涨天数/总天数*100"""
    n = _as_int(n)
    return COUNT(close.diff() > 0, n) / n * 100


def PSYMA(close, n=12, m=6):
    return MA(PSY(close, n), m)


def BBI(close, m1=3, m2=6, m3=12, m4=20):
    """多空指数：四条均线平均"""
    return (MA(close, m1) + MA(close, m2) + MA(close, m3) + MA(close, m4)) / 4


def _dmi_parts(close, high, low, m1=14):
    """DMI 中间量：+DI / -DI"""
    m1 = _as_int(m1)
    up, down = high.diff(), -low.diff()
    pdm = up.where((up > down) & (up > 0), 0.0)
    mdm = down.where((down > up) & (down > 0), 0.0)
    prev_close = close.shift(1)
    tr = np.maximum(
        high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs())
    )
    tr_sum = tr.rolling(m1, min_periods=1).sum().replace(0, np.nan)
    pdi = pdm.rolling(m1, min_periods=1).sum() / tr_sum * 100
    mdi = mdm.rolling(m1, min_periods=1).sum() / tr_sum * 100
    return pdi, mdi


def DMI_PDI(close, high, low, m1=14, m2=6):
    return _dmi_parts(close, high, low, m1)[0]


def DMI_MDI(close, high, low, m1=14, m2=6):
    return _dmi_parts(close, high, low, m1)[1]


def DMI_ADX(close, high, low, m1=14, m2=6):
    pdi, mdi = _dmi_parts(close, high, low, m1)
    dx = (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan) * 100
    return MA(dx, m2)


def DMI_ADXR(close, high, low, m1=14, m2=6):
    adx = DMI_ADX(close, high, low, m1, m2)
    return (adx + adx.shift(_as_int(m2))) / 2


def DEMA(x, n=14):
    """双指数移动平均：2*EMA - EMA(EMA)"""
    e1 = EMA(x, n)
    return 2 * e1 - EMA(e1, n)


def TEMA(x, n=14):
    """三重指数移动平均：3*E1 - 3*E2 + E3"""
    e1 = EMA(x, n)
    e2 = EMA(e1, n)
    e3 = EMA(e2, n)
    return 3 * e1 - 3 * e2 + e3


def KAMA(x, n=14):
    """考夫曼自适应移动平均（快/慢常数 2/30）"""
    n = _as_int(n)
    fast, slow = 2 / (2 + 1), 2 / (30 + 1)

    def _col(s: pd.Series) -> pd.Series:
        vals = s.to_numpy(dtype=float)
        change = np.abs(vals - np.concatenate([np.full(n, np.nan), vals[:-n]]))
        vol = (
            pd.Series(np.abs(np.diff(vals, prepend=np.nan)))
            .rolling(n, min_periods=1)
            .sum()
            .to_numpy()
        )
        er = np.where(vol > 0, change / vol, 0.0)
        sc = (er * (fast - slow) + slow) ** 2
        out = np.full_like(vals, np.nan)
        prev = np.nan
        for i in range(len(vals)):
            if np.isnan(vals[i]):
                continue
            if np.isnan(prev):
                prev = vals[i]
            elif not np.isnan(sc[i]):
                prev = prev + sc[i] * (vals[i] - prev)
            out[i] = prev
        return pd.Series(out, index=s.index)

    if isinstance(x, pd.Series):
        return _col(x)
    return x.apply(_col)


def T3(x, n=14, v=0.7):
    """T3 三重平滑移动平均（容量因子 v=0.7）"""

    def _gd(s):
        return EMA(s, n) * (1 + v) - EMA(EMA(s, n), n) * v

    return _gd(_gd(_gd(x)))


def PPO(a, b):
    """百分比价格振荡器：(快线-慢线)/慢线*100"""
    return (
        (a - b) / b.replace(0, np.nan) * 100
        if hasattr(b, "replace")
        else (a - b) / b * 100
    )


def AROONOSC(x, n=14):
    """阿隆振荡器：AroonUp - AroonDown"""
    n = _as_int(n)
    return (LLVBARS(x, n) - HHVBARS(x, n)) / n * 100


def ADXR(x, n=14):
    """ADX 评级：当前值与 N 期前值的平均"""
    return (x + x.shift(_as_int(n))) / 2


def CMO(x, n=14):
    """钱德动量振荡器：100*(涨幅和-跌幅和)/(涨幅和+跌幅和)"""
    n = _as_int(n)
    delta = x.diff()
    su = delta.clip(lower=0).rolling(n, min_periods=1).sum()
    sd = (-delta.clip(upper=0)).rolling(n, min_periods=1).sum()
    return 100 * (su - sd) / (su + sd).replace(0, np.nan)


def STOCHASTIC(x, n=14):
    """随机振荡器：价格在过去 N 日区间的相对位置"""
    ll, hh = TS_MIN(x, n), TS_MAX(x, n)
    return (x - ll) / (hh - ll).replace(0, np.nan) * 100


def VR(close, volume, m1=26):
    """成交率比率：(涨日量+平日量/2)/(跌日量+平日量/2)*100"""
    m1 = _as_int(m1)
    delta = close.diff()
    av = volume.where(delta > 0, 0.0).rolling(m1, min_periods=1).sum()
    bv = volume.where(delta < 0, 0.0).rolling(m1, min_periods=1).sum()
    cv = volume.where(delta == 0, 0.0).rolling(m1, min_periods=1).sum()
    return (av + cv / 2) / (bv + cv / 2).replace(0, np.nan) * 100


def MFI(close, high, low, volume, n=14):
    """资金流量指标（成交量 RSI）"""
    n = _as_int(n)
    tp = (high + low + close) / 3
    mf = tp * volume
    delta = tp.diff()
    pos = mf.where(delta > 0, 0.0).rolling(n, min_periods=1).sum()
    neg = mf.where(delta < 0, 0.0).rolling(n, min_periods=1).sum()
    return 100 - 100 / (1 + pos / neg.replace(0, np.nan))


def EMV(high, low, volume, n=14, m=9):
    """简易波动指标"""
    mid = (high + low) / 2
    em = mid.diff() * (high - low) / volume.replace(0, np.nan)
    return MA(em, n)


def EMVMA(high, low, volume, n=14, m=9):
    return MA(EMV(high, low, volume, n, m), m)


def TRIX(close, m1=12, m2=9):
    """三重指数平滑平均：三次 EMA 后的变化率*100"""
    tr = EMA(EMA(EMA(close, m1), m1), m1)
    return tr.pct_change() * 100


def TRIMA(close, m1=12, m2=9):
    return MA(TRIX(close, m1, m2), m2)


def DPO(close, m1=20, m2=10, m3=6):
    """区间震荡线：价格 - 前 M2 期的 M1 日均线"""
    return close - MA(close, m1).shift(_as_int(m2))


def DPOMA(close, m1=20, m2=10, m3=6):
    return MA(DPO(close, m1, m2, m3), m3)


def ARBR(open_, close, high, low, m1=26):
    """AR 人气指标：SUM(H-O)/SUM(O-L)*100"""
    m1 = _as_int(m1)
    up = (high - open_).rolling(m1, min_periods=1).sum()
    down = (open_ - low).rolling(m1, min_periods=1).sum()
    return up / down.replace(0, np.nan) * 100


def BRAR(open_, close, high, low, m1=26):
    """BR 意愿指标：SUM(max(0,H-昨收))/SUM(max(0,昨收-L))*100"""
    m1 = _as_int(m1)
    prev_close = close.shift(1)
    up = (high - prev_close).clip(lower=0).rolling(m1, min_periods=1).sum()
    down = (prev_close - low).clip(lower=0).rolling(m1, min_periods=1).sum()
    return up / down.replace(0, np.nan) * 100


def MTM(close, n=12, m=6):
    """动量指标：价格 - N 期前价格"""
    return close - close.shift(_as_int(n))


def MTMMA(close, n=12, m=6):
    return MA(MTM(close, n, m), m)


def MASS(high, low, n1=9, n2=25, m=6):
    """梅斯线：SUM(EMA(H-L,N1)/EMA(EMA(H-L,N1),N1), N2)"""
    rng = high - low
    e1 = EMA(rng, n1)
    e2 = EMA(e1, n1)
    return SUM(e1 / e2.replace(0, np.nan), n2)


def MASSMA(high, low, n1=9, n2=25, m=6):
    return MA(MASS(high, low, n1, n2, m), m)


def ROCMA(close, n=12, m=6):
    return MA(RETURNS(close, n) * 100, m)


def EXPMA(close, n1=12, n2=50):
    return EMA(close, n1)


def EXPMA2(close, n1=12, n2=50):
    return EMA(close, n2)


def _swing_index(open_, close, high, low):
    """ASI 的单期摆动指数 SI"""
    lc = close.shift(1)
    lo = open_.shift(1)
    aa = (high - lc).abs()
    bb = (low - lc).abs()
    cc = (high - low.shift(1)).abs()
    dd = (lc - lo).abs()
    r = np.where(
        (aa > bb) & (aa > cc),
        aa + bb / 2 + dd / 4,
        np.where((bb > cc) & (bb > aa), bb + aa / 2 + dd / 4, cc + dd / 4),
    )
    r = aa * 0 + r  # 保持 DataFrame 结构
    x = close - lc + (close - open_) / 2 + lc - lo
    return 16 * x / r.replace(0, np.nan) * np.maximum(aa, bb)


def ASI(open_, close, high, low, m1=26, m2=10):
    """振动升降指标：SI 的 M1 日累计"""
    return SUM(_swing_index(open_, close, high, low), m1)


def ASIT(open_, close, high, low, m1=26, m2=10):
    return MA(ASI(open_, close, high, low, m1, m2), m2)


def DIF(close, n1=10, n2=50, m=10):
    """差离值：短期 EMA - 长期 EMA"""
    return EMA(close, n1) - EMA(close, n2)


def DFMA(close, n1=10, n2=50, m=10):
    return MA(DIF(close, n1, n2, m), m)


def BOLLINGERDIFF(a, b):
    """布林差值：2 倍差值"""
    return 2 * (a - b)


def build_operator_namespace(
    panels: dict,
    industry_map: dict | None = None,
    fundamental: dict | None = None,
) -> dict:
    """构建公式求值命名空间：基础字段 + vwap/returns + 全部算子（大小写别名）

    panels: {"open","high","low","close","volume","amount"} 面板 DataFrame
    industry_map: 可选 {code: industry}，供 INDUSTRY_NEUTRALIZE 算子使用
    fundamental: 可选 {fund_pb/fund_pe/fund_eps/fund_roe/...}: 点位(公告日)面板，
        使财务/估值因子可直接用 fund_XXX 表达式。
    """
    # 行业映射注入模块全局，供 INDUSTRY_NEUTRALIZE 无参调用时取用
    if industry_map:
        globals()["_ACTIVE_INDUSTRY_MAP"] = industry_map

    close = panels.get("close")
    volume = panels.get("volume")
    amount = panels.get("amount")

    # vwap 近似：成交额 / 成交量
    vwap = None
    if amount is not None and volume is not None:
        vwap = amount.div(volume.replace(0, np.nan))

    ns: dict = {
        "np": np,
        "pd": pd,
        # 基础量价字段（大小写均可）
        "open": panels.get("open"),
        "OPEN": panels.get("open"),
        "high": panels.get("high"),
        "HIGH": panels.get("high"),
        "low": panels.get("low"),
        "LOW": panels.get("low"),
        "close": close,
        "CLOSE": close,
        "volume": volume,
        "VOLUME": volume,
        "amount": amount,
        "AMOUNT": amount,
        "vwap": vwap,
        "VWAP": vwap,
        "returns": close.pct_change() if close is not None else None,
        "RETURNS_": close.pct_change() if close is not None else None,
        "adv20": ADV(volume, 20) if volume is not None else None,
        "ADV20": ADV(volume, 20) if volume is not None else None,
        # 派生参考面板（可基线提供）：市值 / 换手率 / 行业映射（供 INDUSTRY_NEUTRALIZE）
        "market_cap": panels.get("market_cap"),
        "MARKET_CAP": panels.get("market_cap"),
        "turnover": panels.get("turnover"),
        "TURNOVER": panels.get("turnover"),
        # 基本面（公告日点位）字段：fund_pe / fund_pb / fund_eps / fund_roe ...
        **({f: p for f, p in fundamental.items()} if fundamental else {}),
        **({f.upper(): p for f, p in fundamental.items()} if fundamental else {}),
    }

    # 注册全部算子：大写原名 + 小写别名
    operators = {
        "ABS": ABS,
        "LOG": LOG,
        "LOGABS": LOGABS,
        "SIGN": SIGN,
        "SIGNEDPOWER": SIGNEDPOWER,
        "POWER": POWER,
        "AS_FLOAT": AS_FLOAT,
        "RD": RD,
        "SIN": SIN,
        "COS": COS,
        "TAN": TAN,
        "ARCSIN": ARCSIN,
        "ARCCOS": ARCCOS,
        "ARCTAN": ARCTAN,
        "RANK": RANK,
        "SCALE": SCALE,
        "ZSCORE": ZSCORE,
        "INDUSTRY_NEUTRALIZE": INDUSTRY_NEUTRALIZE,
        "DELAY": DELAY,
        "REF": REF,
        "DELTA": DELTA,
        "DIFF": DIFF,
        "MA": MA,
        "SUM": SUM,
        "SUMAC": SUMAC,
        "PRODUCT": PRODUCT,
        "STD": STD,
        "STDDEV": STDDEV,
        "VAR": VAR,
        "TS_MAX": TS_MAX,
        "TS_MIN": TS_MIN,
        "TSMAX": TS_MAX,
        "TSMIN": TS_MIN,
        "TS_MIDDLE": TS_MIDDLE,
        "TS_MEDIAN": TS_MEDIAN,
        "TS_MAD": TS_MAD,
        "AVEDEV": AVEDEV,
        "TS_ZSCORE": TS_ZSCORE,
        "TS_SKEW": TS_SKEW,
        "TS_KURT": TS_KURT,
        "HHV": HHV,
        "LLV": LLV,
        "HHVBARS": HHVBARS,
        "LLVBARS": LLVBARS,
        "TS_RANK": TS_RANK,
        "TSRANK": TS_RANK,
        "TS_ARGMAX": TS_ARGMAX,
        "TS_ARGMIN": TS_ARGMIN,
        "HIGHDAY": HIGHDAY,
        "LOWDAY": LOWDAY,
        "DECAYLINEAR": DECAYLINEAR,
        "DECAY_LINEAR": DECAY_LINEAR,
        "EMA": EMA,
        "WMA": WMA,
        "SMA": SMA,
        "DMA": DMA,
        "TS_MEAN": MA,
        "RETURNS": RETURNS,
        "FUTURE_RETURNS": FUTURE_RETURNS,
        "ROC": ROC,
        "PCT_CHANGE": PCT_CHANGE,
        "COUNT": COUNT,
        "EVERY": EVERY,
        "EXIST": EXIST,
        "BARSSINCEN": BARSSINCEN,
        "CONST": CONST,
        "BARSLAST": BARSLAST,
        "BARSLASTCOUNT": BARSLASTCOUNT,
        "SLOPE": SLOPE,
        "ANGLE": ANGLE,
        "INTERCEPT": INTERCEPT,
        "FORCAST": FORCAST,
        "SHARPE": SHARPE,
        "SUM_ABS_PRICE_CHANGE": SUM_ABS_PRICE_CHANGE,
        "MEAN_ABS_PRICE_CHANGE": MEAN_ABS_PRICE_CHANGE,
        "MAX": MAX,
        "MIN": MIN,
        "MEAN": MEAN,
        "EQUAL": EQUAL,
        "VALUEWHEN": VALUEWHEN,
        "CROSS": CROSS,
        "LONGCROSS": LONGCROSS,
        "LAST": LAST,
        "IF": IF,
        "CORR": CORR,
        "CORRELATION": CORRELATION,
        "COV": COV,
        "COVARIANCE": COVARIANCE,
        "TS_REGRESSION": TS_REGRESSION,
        "SUMIF": SUMIF,
        "REGBETA": REGBETA,
        "REGRESI": REGRESI,
        "ADV": ADV,
        "RSI": RSI,
        "MACD": MACD,
        "MACD_DIF": MACD_DIF,
        "MACD_DEA": MACD_DEA,
        "BOLL_MID": BOLL_MID,
        "BOLL_UPPER": BOLL_UPPER,
        "BOLL_LOWER": BOLL_LOWER,
        "BOLL_WIDTH": BOLL_WIDTH,
        "ATR": ATR,
        "CCI": CCI,
        "WR": WR,
        "BIAS": BIAS,
        "PSY": PSY,
        "PSYMA": PSYMA,
        "BBI": BBI,
        "DMI_PDI": DMI_PDI,
        "DMI_MDI": DMI_MDI,
        "DMI_ADX": DMI_ADX,
        "DMI_ADXR": DMI_ADXR,
        "DEMA": DEMA,
        "TEMA": TEMA,
        "KAMA": KAMA,
        "T3": T3,
        "PPO": PPO,
        "AROONOSC": AROONOSC,
        "ADXR": ADXR,
        "CMO": CMO,
        "STOCHASTIC": STOCHASTIC,
        "VR": VR,
        "MFI": MFI,
        "EMV": EMV,
        "EMVMA": EMVMA,
        "TRIX": TRIX,
        "TRIMA": TRIMA,
        "DPO": DPO,
        "DPOMA": DPOMA,
        "BRAR": BRAR,
        "ARBR": ARBR,
        "MTM": MTM,
        "MTMMA": MTMMA,
        "MASS": MASS,
        "MASSMA": MASSMA,
        "ROCMA": ROCMA,
        "EXPMA": EXPMA,
        "EXPMA2": EXPMA2,
        "ASI": ASI,
        "ASIT": ASIT,
        "DIF": DIF,
        "DFMA": DFMA,
        "BOLLINGERDIFF": BOLLINGERDIFF,
        "KDJ_K": KDJ_K,
        "KDJ_D": KDJ_D,
        "KDJ_J": KDJ_J,
        "OBV": OBV,
    }
    for name, fn in operators.items():
        ns[name] = fn
        ns[name.lower()] = fn  # 小写别名（Alpha191 公式多为小写）

    return ns
