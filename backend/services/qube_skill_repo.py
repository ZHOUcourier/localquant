"""技能仓库信息抓取 — 从技能关联的 GitHub 仓库拉取 README / SKILL.md 与仓库元数据

- 按技能名缓存到 qube_skill_repos 表，TTL 6 小时，避免频繁请求 GitHub。
- 优先 raw.githubusercontent.com（免 API 限额）拉正文；元数据走 GitHub API
  （stars/license/description），失败时降级为空字段，不影响技能浏览。
- README 分支自动探测 main / master；LLMQuant 的 tree 路径会定位到对应
  skills/llmquant-* 子目录并尝试读取其中的 SKILL.md。
"""

import json
import re
import time
from typing import Optional

import httpx
from loguru import logger

from backend.database import get_db

REPO_CACHE_TTL = 6 * 3600  # 秒
DEFAULT_TIMEOUT = 12.0


def parse_repo_url(repo_url: str) -> Optional[dict]:
    """解析 GitHub 仓库 URL → {owner, repo, branch, subpath}

    支持两种形态：
    - https://github.com/owner/repo
    - https://github.com/owner/repo/tree/{branch}/{subpath}
    """
    url = (repo_url or "").strip()
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+)(/.*)?)?", url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2).rstrip(".git")
    branch = m.group(3) or ""
    subpath = (m.group(4) or "").strip("/")
    return {"owner": owner, "repo": repo, "branch": branch, "subpath": subpath}


def _candidate_readme_names() -> list[str]:
    return ["README.md", "readme.md", "Readme.md", "README.rst", "README"]


async def _fetch_raw(client: httpx.AsyncClient, url: str) -> Optional[str]:
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


async def _fetch_readme(client: httpx.AsyncClient, info: dict) -> Optional[str]:
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


async def _fetch_skill_md(client: httpx.AsyncClient, info: dict) -> Optional[str]:
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
    return {
        "ok": True,
        "repo_url": repo_url,
        "owner": info["owner"],
        "repo": info["repo"],
        "branch": info["branch"] or info.get("default_branch", "") or "main",
        "subpath": info["subpath"],
        "readme": readme,
        "skill_md": skill_md,
        "meta": meta,
        "fetched_at": int(time.time()),
    }


async def get_skill_repo(skill_name: str, repo_url: str, force: bool = False) -> dict:
    """取技能的仓库信息（带缓存）；无仓库地址时返回空"""
    if not repo_url:
        return {
            "ok": False,
            "error": "该技能没有关联的 GitHub 仓库",
            "repo_url": "",
        }
    db = await get_db()
    try:
        if not force:
            cursor = await db.execute(
                "SELECT data_json, fetched_at FROM qube_skill_repos WHERE skill_name = ?",
                (skill_name,),
            )
            row = await cursor.fetchone()
            if row and int(time.time()) - row["fetched_at"] < REPO_CACHE_TTL:
                try:
                    payload = json.loads(row["data_json"] or "{}")
                    if payload:
                        return payload
                except Exception:
                    pass
    finally:
        await db.close()

    payload = await _fetch_repo_payload(repo_url)
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
    return payload
