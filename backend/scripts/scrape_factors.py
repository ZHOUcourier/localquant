"""
从参考网站 pandaaiquant.com 抓取全部因子数据，存入本地 SQLite 数据库。

运行方式：
    # 设置环境变量（从浏览器登录后 localStorage 中获取 token）
    export PANDA_TOKEN="your_token_here"
    python -m backend.scripts.scrape_factors

    # 或在 .env 文件中设置 PANDA_TOKEN=xxx
"""

import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ── 加载环境变量 ────────────────────────────────────────────────────────────────
load_dotenv()

# ── 常量 ──────────────────────────────────────────────────────────────────────
BASE_URL = "https://www.pandaaiquant.com/pandaApi/factorCenter"
CATEGORY_API = f"{BASE_URL}/getQuantFactorCategory"
FACTOR_LIST_API = f"{BASE_URL}/getQuantFactorCenterData"

DB_PATH = Path("./data/localquant.db")
PAGE_SIZE = 30

# 9 大分类（备用，若 API 失败则使用）
FALLBACK_CATEGORIES = [
    {
        "categoryCode": "TECHNICAL",
        "categoryName": "技术类因子",
        "colorHex": "#5FA5FA",
        "factorCount": 79,
    },
    {
        "categoryCode": "VALUATION",
        "categoryName": "估值因子",
        "colorHex": "#2E8E6C",
        "factorCount": 10,
    },
    {
        "categoryCode": "VOLUME",
        "categoryName": "量能指标因子",
        "colorHex": "#DFAA20",
        "factorCount": 36,
    },
    {
        "categoryCode": "OVERBOUGHT_OVERSOLD",
        "categoryName": "超买超卖因子",
        "colorHex": "#F87171",
        "factorCount": 42,
    },
    {
        "categoryCode": "MA",
        "categoryName": "均线类因子",
        "colorHex": "#23C8E2",
        "factorCount": 81,
    },
    {
        "categoryCode": "BASIC",
        "categoryName": "基础因子",
        "colorHex": "#94A3B8",
        "factorCount": 8,
    },
    {
        "categoryCode": "FINANCIAL_DERIVED",
        "categoryName": "财务指标衍生因子",
        "colorHex": "#F472B6",
        "factorCount": 90,
    },
    {
        "categoryCode": "ALPHA101",
        "categoryName": "Alpha101",
        "colorHex": "#3D66E0",
        "factorCount": 87,
    },
    {
        "categoryCode": "ALPHA191",
        "categoryName": "Alpha191",
        "colorHex": "#86DDD3",
        "factorCount": 175,
    },
]

# 通用请求头
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def get_headers(token: str = "") -> dict:
    """构建请求头，包含认证 token"""
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.pandaaiquant.com",
        "Referer": "https://www.pandaaiquant.com/",
        "Cache-Control": "no-cache",
    }
    if token:
        headers["Authorization"] = token
    return headers


# ── Token 获取 ──────────────────────────────────────────────────────────────────
def get_token() -> str:
    """从环境变量或 .env 文件获取 token"""
    token = os.getenv("PANDA_TOKEN", "").strip()
    if not token:
        print("=" * 60)
        print("  ❌ 未找到 PANDA_TOKEN 环境变量")
        print("=" * 60)
        print()
        print("  参考网站 API 需要认证才能获取因子列表数据。")
        print("  请按以下步骤获取 token：")
        print()
        print("  1. 在浏览器中打开 https://www.pandaaiquant.com")
        print("  2. 登录你的账号")
        print("  3. 按 F12 打开开发者工具")
        print("  4. 切换到 Application (应用) 标签")
        print("  5. 在左侧找到 Local Storage > https://www.pandaaiquant.com")
        print("  6. 找到 key 为 'token' 的值，复制它")
        print("  7. 设置环境变量：")
        print('     export PANDA_TOKEN="你复制的token值"')
        print("     或在 .env 文件中添加：PANDA_TOKEN=你复制的token值")
        print()
        print("=" * 60)
        sys.exit(1)
    return token


# ── 数据库初始化 ────────────────────────────────────────────────────────────────
def init_tables(conn: sqlite3.Connection):
    """确保目标表存在"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS preset_factor_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_code TEXT UNIQUE NOT NULL,
            category_name TEXT NOT NULL,
            color_hex TEXT,
            factor_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS preset_factors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factor_code TEXT UNIQUE NOT NULL,
            factor_name TEXT NOT NULL,
            category_id INTEGER,
            category_code TEXT,
            category_name TEXT,
            category_color_hex TEXT,
            description TEXT,
            ic_mean REAL,
            rank_ic REAL,
            ic_ir REAL,
            ic_std REAL,
            annualized_return REAL,
            maximum_drawdown REAL,
            sharpe_ratio REAL,
            turnover_rate REAL,
            start_date TEXT,
            data_date TEXT,
            stock_pool TEXT,
            is_preset BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


# ── API 调用 ────────────────────────────────────────────────────────────────────
async def fetch_categories(client: httpx.AsyncClient, token: str) -> list[dict]:
    """获取分类列表（无需认证）"""
    print("[1/3] 获取因子分类列表...")
    headers = get_headers(token)
    resp = await client.get(CATEGORY_API, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # 解析返回格式: {"code": "200", "data": {"categoryTotal": 608, "list": [...]}}
    items = []
    if isinstance(data, dict):
        raw_data = data.get("data") or {}
        if isinstance(raw_data, dict):
            items = raw_data.get("list") or []
        elif isinstance(raw_data, list):
            items = raw_data

    if not items:
        print("  ⚠️  API 未返回分类数据，使用备用分类列表")
        return FALLBACK_CATEGORIES

    print(f"  ✅ 获取到 {len(items)} 个分类")
    for cat in items:
        print(
            f"     - {cat.get('categoryName', '?')} ({cat.get('categoryCode', '?')}): {cat.get('factorCount', '?')} 个因子"
        )
    return items


async def fetch_all_factors(client: httpx.AsyncClient, token: str) -> list[dict]:
    """
    获取全部因子数据。
    优先尝试一次性拉取全量（categoryCode 为空），
    若失败则回退到按分类分页获取。
    """
    print("\n[2/3] 获取全部因子列表...")
    headers = get_headers(token)

    # 方式1：一次性获取全量
    payload = {
        "page": 1,
        "pageSize": 200,
        "categoryCode": "",
        "market": "A",
        "period": "近一年",
        "sortField": "RANK_IC",
        "sortOrder": "desc",
    }

    try:
        resp = await client.post(
            FACTOR_LIST_API, json=payload, headers=headers, timeout=60
        )
        resp.raise_for_status()
        data = resp.json()

        items, total = _parse_factor_response(data)
        if items:
            print(f"  ✅ 第 1 页获取到 {len(items)} 个因子（API 报告总数: {total}）")
            # 如果一次没拿完，继续分页
            if total > len(items):
                more = await _fetch_remaining(client, headers, total, len(items))
                items.extend(more)
            return items
    except httpx.HTTPStatusError as e:
        print(
            f"  ⚠️  一次性获取失败 (HTTP {e.response.status_code})，回退到按分类分页获取..."
        )
    except Exception as e:
        print(f"  ⚠️  一次性获取失败: {e}，回退到按分类分页获取...")

    # 方式2：按分类分页获取
    return await fetch_factors_by_category(client, token)


async def _fetch_remaining(
    client: httpx.AsyncClient, headers: dict, total: int, fetched_count: int
) -> list[dict]:
    """继续分页获取剩余因子"""
    items = []
    page = 2  # 第 1 页已获取
    page_size = 200  # API 实际最大返回 200 条
    while fetched_count + len(items) < total:
        payload = {
            "page": page,
            "pageSize": page_size,
            "categoryCode": "",
            "market": "A",
            "period": "近一年",
            "sortField": "RANK_IC",
            "sortOrder": "desc",
        }
        resp = await client.post(
            FACTOR_LIST_API, json=payload, headers=headers, timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        page_items, _ = _parse_factor_response(data)
        if not page_items:
            break
        items.extend(page_items)
        print(
            f"      第 {page} 页: 获取 {len(page_items)} 条（累计 {fetched_count + len(items)}/{total}）"
        )
        if len(page_items) < page_size:
            break
        page += 1
    return items


async def fetch_factors_by_category(
    client: httpx.AsyncClient, token: str
) -> list[dict]:
    """按分类分页获取全部因子"""
    headers = get_headers(token)
    categories = await fetch_categories(client, token)
    all_factors = []

    for idx, cat in enumerate(categories, 1):
        code = cat.get("categoryCode", "")
        name = cat.get("categoryName", "")
        expected = cat.get("factorCount", 0)
        print(
            f"\n  [{idx}/{len(categories)}] 分类: {name} ({code})，预期 {expected} 个因子"
        )

        page = 1
        cat_factors = []

        while True:
            payload = {
                "page": page,
                "pageSize": PAGE_SIZE,
                "categoryCode": code,
                "market": "A",
                "period": "近一年",
                "sortField": "RANK_IC",
                "sortOrder": "desc",
            }

            resp = await client.post(
                FACTOR_LIST_API, json=payload, headers=headers, timeout=60
            )
            resp.raise_for_status()
            data = resp.json()

            items, total = _parse_factor_response(data)
            if not items:
                break

            cat_factors.extend(items)
            print(
                f"      第 {page} 页: 获取 {len(items)} 条（累计 {len(cat_factors)}/{total}）"
            )

            if len(cat_factors) >= total or len(items) < PAGE_SIZE:
                break
            page += 1

        print(f"    ✅ {name}: 共获取 {len(cat_factors)} 个因子")
        all_factors.extend(cat_factors)

    return all_factors


def _parse_factor_response(data: dict) -> tuple[list[dict], int]:
    """解析因子列表 API 返回数据，返回 (items, total)"""
    items = []
    total = 0
    if isinstance(data, dict):
        raw = data.get("data") or data.get("result") or {}
        if isinstance(raw, dict):
            items = raw.get("list") or raw.get("items") or raw.get("records") or []
            total = raw.get("total", len(items))
        elif isinstance(raw, list):
            items = raw
            total = len(items)
    return items, total


# ── 数据入库 ────────────────────────────────────────────────────────────────────
def save_categories(conn: sqlite3.Connection, categories: list[dict]):
    """保存分类数据"""
    print("\n[3/3] 保存数据到 SQLite...")
    inserted_cat = 0
    for cat in categories:
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO preset_factor_categories
                    (category_code, category_name, color_hex, factor_count)
                VALUES (?, ?, ?, ?)
            """,
                (
                    cat.get("categoryCode"),
                    cat.get("categoryName"),
                    cat.get("colorHex"),
                    cat.get("factorCount", 0),
                ),
            )
            inserted_cat += 1
        except Exception as e:
            print(f"  ⚠️  分类插入失败 [{cat.get('categoryCode')}]: {e}")
    conn.commit()
    print(f"  ✅ 分类入库完成: {inserted_cat} 条")


def save_factors(conn: sqlite3.Connection, factors: list[dict]):
    """保存因子数据"""
    inserted = 0
    skipped = 0
    now = datetime.utcnow().isoformat()

    for f in factors:
        code = f.get("factorCode")
        name = f.get("factorName")
        if not code or not name:
            skipped += 1
            continue

        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO preset_factors
                    (factor_code, factor_name, category_id, category_code, category_name,
                     category_color_hex, description,
                     ic_mean, rank_ic, ic_ir, ic_std,
                     annualized_return, maximum_drawdown, sharpe_ratio, turnover_rate,
                     start_date, data_date, stock_pool, is_preset, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
                (
                    code,
                    name,
                    f.get("categoryId"),
                    f.get("categoryCode"),
                    f.get("categoryName"),
                    f.get("categoryColorHex"),
                    f.get("description"),
                    f.get("icMean"),
                    f.get("rankIc"),
                    f.get("icIr"),
                    f.get("icStd"),
                    f.get("annualizedReturn"),
                    f.get("maximumDrawdown"),
                    f.get("sharpeRatio"),
                    f.get("turnoverRate"),
                    f.get("startDate"),
                    f.get("dataDate"),
                    f.get("stockPool"),
                    now,
                ),
            )
            inserted += 1
        except Exception as e:
            print(f"  ⚠️  因子插入失败 [{code}]: {e}")
            skipped += 1

    conn.commit()
    print(f"  ✅ 因子入库完成: {inserted} 条成功, {skipped} 条跳过")


def verify_data(conn: sqlite3.Connection):
    """验证入库数据"""
    cur = conn.execute("SELECT COUNT(*) FROM preset_factors")
    factor_count = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM preset_factor_categories")
    cat_count = cur.fetchone()[0]
    cur = conn.execute("""
        SELECT category_code, category_name, factor_count,
               (SELECT COUNT(*) FROM preset_factors pf WHERE pf.category_code = pfc.category_code) as actual_count
        FROM preset_factor_categories pfc
        ORDER BY factor_count DESC
    """)
    print("\n📊 入库验证:")
    print(f"   preset_factor_categories: {cat_count} 条分类")
    print(f"   preset_factors:           {factor_count} 条因子")
    print()
    print("   各分类因子数量 (预期 / 实际):")
    for row in cur.fetchall():
        status = "✅" if row[2] == row[3] else "⚠️"
        print(f"   {status} {row[1]:<16} ({row[0]}): {row[2]:>3} / {row[3]:>3}")


# ── 主函数 ──────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("  参考网站因子数据抓取工具")
    print("  目标: pandaaiquant.com 全量因子数据")
    print("=" * 60)

    # 获取认证 token
    token = get_token()
    print(
        f"\n🔑 Token 已配置: {token[:8]}...{token[-4:]}"
        if len(token) > 12
        else f"\n🔑 Token 已配置"
    )

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_tables(conn)

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(60.0, connect=30.0),
    ) as client:
        # 1. 获取分类
        categories = await fetch_categories(client, token)

        # 2. 获取全量因子
        factors = await fetch_all_factors(client, token)

    if not factors:
        print("\n❌ 未获取到任何因子数据，请检查：")
        print("   1. Token 是否有效（可能已过期，需重新登录获取）")
        print("   2. 网络连接是否正常")
        print("   3. API 是否可用")
        sys.exit(1)

    # 3. 入库
    save_categories(conn, categories)
    save_factors(conn, factors)

    # 4. 验证
    verify_data(conn)
    conn.close()

    print("\n" + "=" * 60)
    print("  ✅ 抓取任务完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
