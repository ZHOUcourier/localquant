"""把全部内置技能的 GitHub 原文（README/SKILL.md）回填到本地仓（qube_skill_repos）

日常由后端启动时的后台 sweeper 增量补齐；本脚本用于首次初始化或强制全量刷新：
    uv run python -m backend.scripts.backfill_skill_origins            # 只补缺失/过期/失败项
    uv run python -m backend.scripts.backfill_skill_origins --force    # 全部强制刷新
读取永远走本地（use_skill 不联网）；本脚本只是离线可用性的补给通道。
"""

import argparse
import asyncio

from backend.database import init_db
from backend.services.qube_skill_repo import refresh_stale_skill_repos


async def main(force: bool) -> None:
    await init_db()
    results = await refresh_stale_skill_repos(max_age=0 if force else 6 * 3600)
    if not results:
        print("本地仓已是最新，无需回填")
        return
    ok = 0
    for r in results:
        mark = "✓" if r.get("ok") else "✗"
        parts = [f"{mark} {r['name']}"]
        if r.get("ok"):
            parts.append(
                f"readme={'有' if r.get('has_readme') else '无'} "
                f"skill_md={'有' if r.get('has_skill_md') else '无'}"
            )
            ok += 1
        else:
            parts.append(f"失败: {r.get('error') or '未知'}")
        print("  ".join(parts))
    print(f"\n完成：{ok}/{len(results)} 成功")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="忽略缓存年龄，全部强制刷新")
    asyncio.run(main(parser.parse_args().force))
