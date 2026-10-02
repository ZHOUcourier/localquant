"""技能仓库原文 — 本地优先的永久快照仓 + 尽力而为的后台刷新

设计（offline-first）：
- qube_skill_repos 表是「永久本地仓」：抓取成功后的 README / SKILL.md 全文落库，
  读取永远走本地、不依赖网络（use_skill 工具与技能详情页均如此）。
- 联网刷新是尽力而为，只在三处发生：启动后台 sweeper（main.py lifespan）、
  CLI 回填脚本、技能详情页 refresh=true。抓取失败不覆盖既有好快照
  （保留 last-known-good），仅记录 refresh_error。
- REPO_CACHE_TTL 只表示「多久该刷新一次」，不再使本地快照失效。
"""

import asyncio
import json
import re
import time

import httpx
from loguru import logger

from backend.database import get_db

REPO_CACHE_TTL = 6 * 3600  # 秒
DEFAULT_TIMEOUT = 12.0

# 后台刷新任务引用（防 GC）
_refresh_tasks: set[asyncio.Task] = set()


def parse_repo_url(repo_url: str) -> dict | None:
    """解析 GitHub 仓库 URL → {owner, repo, branch, subpath}

    支持两种形态：
    - https://github.com/owner/repo
    - https://github.com/owner/repo/tree/{branch}/{subpath}
    """
    url = (repo_url or "").strip()
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+)(/.*)?)?", url)
    if not m:
        return None
    # 用 removesuffix 剥掉 .git 后缀；rstrip 是按字符集剥尾，会把 overfit→overf 这类
    # 以 t/i/g 结尾的仓库名剪坏（qs-factor-mining / qs-backtest-overfit 曾因此抓取失败）
    owner, repo = m.group(1), m.group(2).removesuffix(".git")
    branch = m.group(3) or ""
    subpath = (m.group(4) or "").strip("/")
    return {"owner": owner, "repo": repo, "branch": branch, "subpath": subpath}


def _candidate_readme_names() -> list[str]:
    return ["README.md", "readme.md", "Readme.md", "README.rst", "README"]


async def _fetch_raw(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url)
    except httpx.HTTPError as e:
        logger.warning(f"抓取技能仓库失败 {url}: {e}")
        return None
    if resp.status_code != 200:
        return None
    text = resp.text
    if len(text) > 60_000:
        text = text[:60_000]
    return text


async def _fetch_readme(client: httpx.AsyncClient, info: dict) -> str | None:
    base = f"https://raw.githubusercontent.com/{info['owner']}/{info['repo']}"
    branches = [info["branch"]] if info["branch"] else []
    branches += [b for b in ("main", "master") if b not in branches]
    # 子目录技能：优先读子目录内的 README，读不到回退仓库根 README
    for branch in branches:
        if info["subpath"]:
            for name in _candidate_readme_names():
                url = f"{base}/{branch}/{info['subpath']}/{name}"
                text = await _fetch_raw(client, url)
                if text:
                    return text
        for name in _candidate_readme_names():
            url = f"{base}/{branch}/{name}"
            text = await _fetch_raw(client, url)
            if text:
                return text
    return None


async def _fetch_skill_md(client: httpx.AsyncClient, info: dict) -> str | None:
    """拉取技能本体 SKILL.md：子目录技能优先子目录，否则仓库根目录"""
    base = f"https://raw.githubusercontent.com/{info['owner']}/{info['repo']}"
    branches = [info["branch"]] if info["branch"] else []
    branches += [b for b in ("main", "master") if b not in branches]
    for branch in branches:
        if info["subpath"]:
            url = f"{base}/{branch}/{info['subpath']}/SKILL.md"
            text = await _fetch_raw(client, url)
            if text:
                return text
        url = f"{base}/{branch}/SKILL.md"
        text = await _fetch_raw(client, url)
        if text:
            return text
    return None


async def _fetch_repo_meta(client: httpx.AsyncClient, info: dict) -> dict:
    url = f"https://api.github.com/repos/{info['owner']}/{info['repo']}"
    try:
        resp = await client.get(url)
    except httpx.HTTPError as e:
        logger.warning(f"获取 GitHub 仓库元数据失败 {url}: {e}")
        return {}
    if resp.status_code != 200:
        return {}
    try:
        data = resp.json()
    except Exception:
        return {}
    license_info = data.get("license") or {}
    return {
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "license": license_info.get("spdx_id") or license_info.get("name") or "",
        "description": data.get("description") or "",
        "language": data.get("language") or "",
        "updated_at": data.get("pushed_at") or "",
        "html_url": data.get("html_url") or "",
        "default_branch": data.get("default_branch") or "",
    }


async def _fetch_repo_payload(repo_url: str) -> dict:
    """联网抓取一次仓库原文与元数据；正文与元数据全空时视为失败（ok=False）"""
    info = parse_repo_url(repo_url)
    if not info:
        return {
            "ok": False,
            "error": f"无法解析仓库地址: {repo_url}",
            "repo_url": repo_url,
        }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        readme = await _fetch_readme(client, info)
        skill_md = await _fetch_skill_md(client, info)
        meta = await _fetch_repo_meta(client, info)
    ok = bool(readme or skill_md or meta)
    return {
        "ok": ok,
        "error": "" if ok else "README/SKILL.md/元数据均未抓到（网络不可达或仓库不存在）",
        "repo_url": repo_url,
        "owner": info["owner"],
        "repo": info["repo"],
        "branch": info["branch"] or (meta.get("default_branch") if meta else "") or "main",
        "subpath": info["subpath"],
        "readme": readme,
        "skill_md": skill_md,
        "meta": meta,
        "fetched_at": int(time.time()),
    }


async def read_skill_repo(skill_name: str) -> dict | None:
    """只读本地快照（无论新旧，不联网）；无快照返回 None"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT data_json FROM qube_skill_repos WHERE skill_name = ?",
            (skill_name,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()
    if not row:
        return None
    try:
        payload = json.loads(row["data_json"] or "{}")
    except Exception:
        return None
    return payload or None


async def _persist_repo_payload(skill_name: str, payload: dict) -> None:
    """落库快照；新结果失败且本地已有好快照时保留 last-known-good 不覆盖"""
    existing = await read_skill_repo(skill_name)
    if existing and existing.get("ok") and not payload.get("ok"):
        return
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO qube_skill_repos (skill_name, data_json, fetched_at) "
            "VALUES (?, ?, ?) ON CONFLICT(skill_name) DO UPDATE SET "
            "data_json = excluded.data_json, fetched_at = excluded.fetched_at",
            (skill_name, json.dumps(payload, ensure_ascii=False), int(time.time())),
        )
        await db.commit()
    finally:
        await db.close()


async def get_skill_repo(skill_name: str, repo_url: str, force: bool = False) -> dict:
    """本地优先取技能原文快照；无快照或 force=True 时联网抓取

    - 有快照且非 force：直接返回（附 stale 标记），零网络等待
    - 联网抓取失败但存在旧好快照：返回旧快照并附 refresh_error
    """
    cached = await read_skill_repo(skill_name)
    if cached and cached.get("ok") and not force:
        age = int(time.time()) - int(cached.get("fetched_at") or 0)
        return {**cached, "stale": age > REPO_CACHE_TTL}
    if not repo_url:
        return {
            "ok": False,
            "error": "该技能没有关联的 GitHub 仓库",
            "repo_url": "",
        }

    payload = await _fetch_repo_payload(repo_url)
    await _persist_repo_payload(skill_name, payload)
    if not payload.get("ok") and cached and cached.get("ok"):
        return {
            **cached,
            "stale": True,
            "refresh_error": payload.get("error") or "刷新失败",
        }
    return payload


def schedule_refresh(skill_name: str, repo_url: str) -> None:
    """安排一次后台刷新（fire-and-forget，绝不阻塞调用方）；无事件循环时静默跳过"""
    if not repo_url:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(get_skill_repo(skill_name, repo_url, force=True))
    _refresh_tasks.add(task)
    task.add_done_callback(_refresh_tasks.discard)


async def refresh_stale_skill_repos(max_age: int = REPO_CACHE_TTL) -> list[dict]:
    """回填/刷新所有启用技能的本地原文仓（启动 sweeper 与 CLI 回填共用）

    逐个处理：快照缺失、上次抓取失败、或超过 max_age 未更新的技能联网刷新；
    单项失败不影响其余。返回每项结果清单。
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT name, repo_url FROM qube_skills "
            "WHERE enabled = 1 AND repo_url != '' ORDER BY id"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    now = int(time.time())
    results: list[dict] = []
    for r in rows:
        cached = await read_skill_repo(r["name"])
        age = now - int(cached.get("fetched_at") or 0) if cached else None
        needs = cached is None or not cached.get("ok") or (age is None or age > max_age)
        if not needs:
            continue
        try:
            payload = await _fetch_repo_payload(r["repo_url"])
            await _persist_repo_payload(r["name"], payload)
            results.append(
                {
                    "name": r["name"],
                    "ok": bool(payload.get("ok")),
                    "has_readme": bool(payload.get("readme")),
                    "has_skill_md": bool(payload.get("skill_md")),
                    "error": payload.get("error", ""),
                }
            )
        except Exception as e:  # 单项失败不阻断回填
            results.append(
                {"name": r["name"], "ok": False, "error": str(e)[:200]}
            )
    return results
