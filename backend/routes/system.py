"""系统资源监控路由

为「因子研究」页提供实时资源占用：CPU（分核心）、内存（物理 + 虚拟/交换）、
磁盘（因子运算占用）、GPU（NVIDIA 可用时）。全部为真实读数，无模拟数据。
"""

import subprocess
from pathlib import Path

import psutil
from fastapi import APIRouter

from backend.config import settings

router = APIRouter()


def _dir_size(path: Path) -> int:
    """递归统计目录字节大小（不存在返回 0）"""
    total = 0
    if path.exists():
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    return total


def _gpu_info() -> dict:
    """GPU 读数：优先 NVIDIA (nvidia-smi)；不可用则明确说明，不伪造数据"""
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            gpus = []
            for line in out.stdout.strip().splitlines():
                parts = [x.strip() for x in line.split(",")]
                if len(parts) >= 4:
                    gpus.append(
                        {
                            "name": parts[0],
                            "util": float(parts[1]),
                            "mem_used_mb": float(parts[2]),
                            "mem_total_mb": float(parts[3]),
                            "temperature": float(parts[4]) if len(parts) > 4 else None,
                        }
                    )
            if gpus:
                return {"available": True, "gpus": gpus}
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass
    return {
        "available": False,
        "reason": "未检测到 NVIDIA GPU（Apple 芯片等集成 GPU 无标准查询接口）",
    }


@router.get("/resources")
async def system_resources():
    """当前系统资源占用快照"""
    # CPU：每核心利用率（0.1s 采样窗口）
    per_core = psutil.cpu_percent(interval=0.1, percpu=True)
    freq = psutil.cpu_freq()

    # 内存：物理内存 + 虚拟内存（交换区）
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()

    # 磁盘：因子运算占用（行情缓存 + 运行产物 + 实验），及所在盘容量
    cache = _dir_size(settings.cache_dir)
    outputs = _dir_size(settings.output_dir)
    experiments = _dir_size(settings.experiment_dir)
    try:
        anchor = settings.data_dir if settings.data_dir.exists() else Path(".")
        disk = psutil.disk_usage(str(anchor))
        device = {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        }
    except OSError:
        device = {"total": 0, "used": 0, "free": 0, "percent": 0}

    return {
        "cpu": {
            "per_core": [round(c, 1) for c in per_core],
            "count": len(per_core),
            "avg": round(sum(per_core) / len(per_core), 1) if per_core else 0.0,
            "freq_mhz": round(freq.current, 0) if freq else None,
        },
        "memory": {
            "physical": {"used": vm.used, "total": vm.total, "percent": vm.percent},
            "virtual": {"used": sm.used, "total": sm.total, "percent": sm.percent},
        },
        "disk": {
            "cache": cache,
            "outputs": outputs,
            "experiments": experiments,
            "factor_total": cache + outputs + experiments,
            "device": device,
        },
        "gpu": _gpu_info(),
    }
