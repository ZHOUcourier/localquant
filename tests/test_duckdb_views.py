"""DuckDB 统一行情视图测试（P0-3）

验证：
- quotes_<周期> 视图把日期索引规范成 trade_date、文件名解析成 code；
- 4 条内置 SQL 模板可直接执行（不再报 Referenced column "index" not found）；
- /api/explorer/schema 字段字典含 trade_date / code；
- 只读护栏仍拒绝写操作。

本地无行情缓存时整组跳过。
"""

import asyncio
import re
from pathlib import Path

import pytest

from backend.config import settings
from backend.services.duckdb_service import DuckDBService, quote_view

svc = DuckDBService()


def _has_quote_cache() -> bool:
    cd = Path(settings.cache_dir)
    if not cd.exists():
        return False
    return any(p.suffix == ".parquet" for sub in cd.iterdir() if sub.is_dir() for p in sub.iterdir())


pytestmark = pytest.mark.skipif(
    not _has_quote_cache(), reason="本地无行情 Parquet 缓存"
)

_CODE_RE = re.compile(r"^\d{6}\.(SZ|SH|BJ)$")


def _first_quote_period() -> str:
    """返回第一个含行情（有 open/close 列）的周期目录名"""
    import duckdb

    cd = Path(settings.cache_dir)
    for sub in sorted(cd.iterdir()):
        if not sub.is_dir():
            continue
        files = sorted(sub.glob("*.parquet"))
        if not files:
            continue
        conn = duckdb.connect()
        try:
            cols = {
                r[0]
                for r in conn.execute(
                    f"DESCRIBE SELECT * FROM read_parquet('{files[0]}')"
                ).fetchall()
            }
        finally:
            conn.close()
        if "open" in cols and "close" in cols:
            return sub.name
    pytest.skip("无行情周期目录")


def test_view_exposes_trade_date_code_ohlcv():
    """视图查询返回 trade_date/code/OHLCV 列，code 形如 000001.SZ"""
    period = _first_quote_period()
    view = quote_view(period)
    r = svc.query_local(f"SELECT trade_date, code, open, close FROM {view} LIMIT 5")
    assert r.get("error") is None, r.get("error")
    assert r["columns"][:4] == ["trade_date", "code", "open", "close"]
    assert r["row_count"] >= 1
    for row in r["data"]:
        assert _CODE_RE.match(row[1]), f"code 解析异常: {row[1]}"


def test_view_single_stock_filter():
    """用视图中真实存在的 code 过滤，能取到该股票数据"""
    period = _first_quote_period()
    view = quote_view(period)
    one = svc.query_local(f"SELECT DISTINCT code FROM {view} LIMIT 1")
    assert one["row_count"] >= 1
    code = one["data"][0][0]
    r = svc.query_local(
        f"SELECT trade_date, close FROM {view} WHERE code = '{code}' "
        f"ORDER BY trade_date DESC LIMIT 5"
    )
    assert r.get("error") is None, r.get("error")
    assert r["row_count"] >= 1


def test_view_cross_section_by_date():
    """用视图中真实存在的最新交易日做截面过滤，能取到多只股票"""
    period = _first_quote_period()
    view = quote_view(period)
    mx = svc.query_local(f"SELECT MAX(trade_date) FROM {view}")
    assert mx["row_count"] >= 1 and mx["data"][0][0]
    latest = str(mx["data"][0][0])[:10]  # YYYY-MM-DD
    r = svc.query_local(
        f"SELECT count(*) FROM {view} WHERE CAST(trade_date AS DATE) = '{latest}'"
    )
    assert r.get("error") is None, r.get("error")
    assert r["data"][0][0] >= 1


def test_builtin_templates_execute():
    """4 条内置模板可直接执行（语法对视图有效），不再报 index 列错误"""
    from backend.routes.explorer import SQL_TEMPLATES

    assert len(SQL_TEMPLATES) >= 4
    for t in SQL_TEMPLATES:
        r = svc.query_local(t["sql"])
        assert r.get("error") is None, f"模板 {t['id']} 执行失败: {r.get('error')}"


def test_schema_field_dictionary_has_view_columns():
    """/api/explorer/schema 字段字典含 trade_date/code，quotes 表 fields 前置这两列"""
    from backend.routes.explorer import explorer_schema

    schema = asyncio.run(explorer_schema())
    fd = schema["field_dictionary"]
    assert "trade_date" in fd and "code" in fd
    quote_tables = [t for t in schema["tables"] if t.get("kind") == "quotes"]
    assert quote_tables, "应至少有一个行情表"
    for t in quote_tables:
        names = [f["name"] for f in t["fields"]]
        assert names[0] == "trade_date" and names[1] == "code"
        assert t.get("view", "").startswith("quotes_")


def test_readonly_guard_rejects_write():
    """只读护栏：写操作（DROP 等）被拒"""
    r = svc.query_local("DROP TABLE quotes_1d")
    assert r.get("error")
    assert r["row_count"] == 0
