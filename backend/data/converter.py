"""数据标准化工具

提供时间戳转换、字段名映射、DataFrame 序列化等通用功能。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def conv_time(timestamp_ms: int | float) -> str:
    """毫秒时间戳转 "20240101150000" 格式字符串

    Args:
        timestamp_ms: 毫秒级时间戳

    Returns:
        "YYYYMMDDHHmmss" 格式字符串
    """
    dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y%m%d%H%M%S")


def normalize_timestamp(index: pd.Index) -> pd.DatetimeIndex:
    """将各种时间索引统一转为 DatetimeIndex

    支持：整数（毫秒时间戳）、字符串日期、已有 DatetimeIndex。
    """
    if isinstance(index, pd.DatetimeIndex):
        return index

    # 整数索引 → 毫秒时间戳
    if pd.api.types.is_integer_dtype(index) or pd.api.types.is_float_dtype(index):
        return pd.to_datetime(index.astype("int64"), unit="ms", utc=True)

    # 字符串或其他 → 尝试解析
    return pd.to_datetime(index)


def normalize_kline_fields(df: pd.DataFrame) -> pd.DataFrame:
    """K 线字段名标准化

    将 xtquant 返回的字段名统一为小写下划线风格。
    常见映射: open/high/low/close/volume/amount 等。
    """
    if df.empty:
        return df

    rename_map: dict[str, str] = {}
    col_lower = {c.lower(): c for c in df.columns}

    # 标准字段映射（xtquant 原始 → 标准化）
    field_aliases = {
        "open": ["open", "开盘价", "开盘"],
        "high": ["high", "最高价", "最高"],
        "low": ["low", "最低价", "最低"],
        "close": ["close", "收盘价", "收盘"],
        "volume": ["volume", "vol", "成交量", "成交量(手)"],
        "amount": ["amount", "成交额", "成交额(元)"],
        "turnover": ["turnover", "换手率"],
    }

    for standard_name, aliases in field_aliases.items():
        for alias in aliases:
            if alias in col_lower and alias != standard_name:
                rename_map[col_lower[alias]] = standard_name
                break

    df = df.rename(columns=rename_map)
    return df


def normalize_tick_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Tick 字段名标准化

    将 xtquant tick 数据的字段名统一。
    """
    if df.empty:
        return df

    rename_map: dict[str, str] = {}
    col_lower = {c.lower(): c for c in df.columns}

    tick_aliases = {
        "last_price": ["lastprice", "last_price", "最新价", "现价"],
        "open": ["open", "开盘价"],
        "high": ["high", "最高价"],
        "low": ["low", "最低价"],
        "volume": ["volume", "vol", "成交量", "总量"],
        "amount": ["amount", "成交额", "总金额"],
        "bid_price": ["bidprice", "bid_price"],
        "ask_price": ["askprice", "ask_price"],
        "bid_vol": ["bidvol", "bid_vol"],
        "ask_vol": ["askvol", "ask_vol"],
    }

    for standard_name, aliases in tick_aliases.items():
        for alias in aliases:
            if alias in col_lower and alias != standard_name:
                rename_map[col_lower[alias]] = standard_name
                break

    df = df.rename(columns=rename_map)
    return df


def df_to_serializable(df: pd.DataFrame) -> dict:
    """将 DataFrame 转为 JSON 可序列化格式

    Returns:
        {"columns": [...], "index": [...], "data": [[...], ...]}
    """
    if df.empty:
        return {"columns": [], "index": [], "data": []}

    # 处理索引
    index_values = []
    for v in df.index:
        if isinstance(v, pd.Timestamp):
            index_values.append(v.isoformat())
        else:
            index_values.append(str(v))

    # 处理数据（NaN → None）
    data = []
    for row in df.itertuples(index=False):
        data.append([
            None if (isinstance(v, float) and pd.isna(v)) else v
            for v in row
        ])

    return {
        "columns": list(df.columns),
        "index": index_values,
        "data": data,
    }
