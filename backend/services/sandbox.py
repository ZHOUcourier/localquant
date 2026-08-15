"""AI/用户信号代码执行 — OpenSandbox 容器隔离，Docker 不可用时降级进程内

方案（与用户确认）：
- 现成轮子 OpenSandbox（阿里，Apache-2.0），容器级隔离，支持 Windows（Docker
  Desktop + WSL2 后端）；不挂载数据卷（Windows 路径易踩坑），改用其文件 API
  把本次回测需要的行情面板以 CSV 传入沙箱，跑完把信号 CSV 读回宿主机。
- 仅用于 QUBE / 回测相关的代码执行（/backtest/run-strategy 与 QUBE run_backtest 工具）。
- Docker / opensandbox-server 不可用时：降级为进程内执行 + 明确警告（不阻断），
  该时刻无容器隔离；执行不设超时（回测本就重）。

区分两类失败：
- SandboxInfraError：沙箱基础设施不可用（未装包 / 未起 server / Docker 未就绪）→ 降级
- ValueError：用户信号代码本身有问题（未定义函数 / 运行报错）→ 直接上抛给调用方
"""

import asyncio
import io
import time
from urllib.parse import urlparse

import pandas as pd
from loguru import logger

from backend.config import settings


class SandboxInfraError(RuntimeError):
    """沙箱基础设施不可用（触发降级，不代表用户代码有错）"""


# 沙箱内运行的信号执行脚本：读入行情 CSV → 执行用户代码 → 调 generate_signals →
# 结果写出 CSV；用户代码异常以 SIGNAL_ERROR 前缀输出到 stdout，供宿主机识别
_RUNNER_TEMPLATE = """\
import sys, traceback
import pandas as pd
import numpy as np

prices = pd.read_csv({prices_path!r}, index_col=0, parse_dates=True)
_user_ns = {{"pd": pd, "np": np}}
try:
    exec({code!r}, _user_ns)
    fn = _user_ns.get("generate_signals")
    if not callable(fn):
        print("SIGNAL_ERROR:信号代码必须定义 generate_signals(prices, **kwargs) 函数")
        sys.exit(0)
    sig = fn(prices)
    if isinstance(sig, dict):
        sig = pd.DataFrame.from_dict(sig, orient="index")
    if not isinstance(sig, pd.DataFrame):
        print("SIGNAL_ERROR:generate_signals 应返回 dict 或 DataFrame")
        sys.exit(0)
    sig.to_csv({signals_path!r})
    print("SIGNAL_OK")
except Exception as e:
    print("SIGNAL_ERROR:" + str(e))
    traceback.print_exc()
"""


def _normalize_signals(sig) -> pd.DataFrame:
    """把 generate_signals 的返回值统一成按日期排序的面板 DataFrame"""
    if isinstance(sig, dict):
        df = pd.DataFrame.from_dict(sig, orient="index")
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    if isinstance(sig, pd.DataFrame):
        return sig
    raise ValueError("generate_signals 应返回 dict 或 DataFrame")


def sandbox_available() -> bool:
    """沙箱是否可能可用（配置开启 + opensandbox 包可导入）；真实可达性在执行时判定"""
    if not settings.sandbox_enabled:
        return False
    try:
        import opensandbox  # noqa: F401
    except Exception:
        return False
    return True


async def _run_in_opensandbox(signal_code: str, prices: pd.DataFrame) -> pd.DataFrame:
    """在 OpenSandbox 容器中执行信号代码，返回信号面板

    任何基础设施层失败抛 SandboxInfraError（触发降级）；用户代码错误抛 ValueError。
    """
    try:
        from opensandbox import Sandbox
        from opensandbox.models import WriteEntry
    except Exception as e:  # 包未安装 → 降级
        raise SandboxInfraError(f"opensandbox 未安装: {e}")

    prices_csv = prices.to_csv()
    prices_path = "/tmp/lq_prices.csv"
    signals_path = "/tmp/lq_signals.csv"
    runner = _RUNNER_TEMPLATE.format(
        prices_path=prices_path, signals_path=signals_path, code=signal_code
    )
    runner_path = "/tmp/lq_runner.py"

    try:
        sandbox = await Sandbox.create(settings.sandbox_image)
    except Exception as e:  # server/Docker 不可用 → 降级
        raise SandboxInfraError(
            f"创建沙箱失败（Docker/opensandbox-server 未就绪？）: {e}"
        )

    try:
        async with sandbox:
            await sandbox.files.write_files(
                [
                    WriteEntry(path=prices_path, data=prices_csv, mode=644),
                    WriteEntry(path=runner_path, data=runner, mode=644),
                ]
            )
            execution = await sandbox.commands.run(f"python {runner_path}")
            stdout = _collect_stdout(execution)
            if "SIGNAL_ERROR:" in stdout:
                msg = stdout.split("SIGNAL_ERROR:", 1)[1].splitlines()[0].strip()
                raise ValueError(f"信号代码执行失败: {msg}")
            content = await sandbox.files.read_file(signals_path)
            text = (
                content.decode()
                if isinstance(content, (bytes, bytearray))
                else str(content)
            )
            return pd.read_csv(io.StringIO(text), index_col=0, parse_dates=True)
    except ValueError:
        raise
    except SandboxInfraError:
        raise
    except Exception as e:  # 执行/读写过程的基础设施异常 → 降级
        raise SandboxInfraError(f"沙箱执行异常: {e}")


def _collect_stdout(execution) -> str:
    """兼容 OpenSandbox 不同返回结构，尽量取出 stdout 文本"""
    try:
        logs = getattr(execution, "logs", None)
        out = getattr(logs, "stdout", None) if logs is not None else None
        if isinstance(out, list):
            return "\n".join(getattr(x, "text", str(x)) for x in out)
        if out is not None:
            return str(out)
        return str(getattr(execution, "stdout", "") or execution)
    except Exception:
        return str(execution)


def _run_in_process(signal_code: str, prices: pd.DataFrame) -> pd.DataFrame:
    """进程内执行（降级路径 / 无 Docker 时）：与沙箱不可用前的原行为一致，不加限制"""
    import numpy as np

    exec_ctx: dict = {}
    exec(signal_code, {"__builtins__": __builtins__, "pd": pd, "np": np}, exec_ctx)  # noqa: S102
    fn = exec_ctx.get("generate_signals")
    if not callable(fn):
        raise ValueError("信号代码必须定义 generate_signals(prices, **kwargs) 函数")
    return _normalize_signals(fn(prices))


async def run_signals(
    signal_code: str, prices: pd.DataFrame
) -> tuple[pd.DataFrame, bool]:
    """执行信号代码，返回 (信号面板, 是否在沙箱中隔离执行)

    - 沙箱可用：容器内执行；用户代码错误抛 ValueError；基础设施故障自动降级
    - 沙箱不可用：进程内执行 + 警告日志
    """
    if sandbox_available():
        try:
            df = await _run_in_opensandbox(signal_code, prices)
            return _normalize_signals(df), True
        except SandboxInfraError as e:
            logger.warning(f"OpenSandbox 不可用，降级为进程内执行（无容器隔离）：{e}")

    import asyncio

    df = await asyncio.to_thread(_run_in_process, signal_code, prices)
    return df, False


_status_cache: dict = {"ts": 0.0, "server_reachable": False, "probe_error": ""}
_STATUS_TTL = 15.0


async def _probe_server() -> tuple[bool, str]:
    """探测 opensandbox-server 是否实际可达（轻量 HTTP，短超时）

    只判断 server 进程/端口是否活着；Docker 与镜像是否可用仍需首次
    创建沙箱时确认，因此返回「可达」而非「保证可用」。
    """
    domain = (settings.sandbox_server_domain or "localhost:8080").strip()
    base = domain if domain.startswith(("http://", "https://")) else f"http://{domain}"
    parsed = urlparse(base)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    error = ""

    try:
        import httpx

        async with httpx.AsyncClient(timeout=1.5) as client:
            for path in ("/v1/ping", "/ping", "/health", "/"):
                url = f"{parsed.scheme}://{host}:{port}{path}"
                try:
                    resp = await client.get(url)
                    if resp.status_code < 500:
                        return True, ""
                except Exception as e:  # noqa: BLE001
                    error = str(e)[:160]
    except Exception as e:  # noqa: BLE001
        error = str(e)[:160]

    # HTTP 探测失败时退回 TCP 探测，区分「端口通但无健康响应」
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=1.2
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return False, f"端口 {host}:{port} 可达，但未返回健康响应"
    except Exception as e:  # noqa: BLE001
        return False, error or str(e)[:160]


async def sandbox_status() -> dict:
    """沙箱状态（供前端/接口展示；实际探测 server，不把「可能可用」当「就绪」）"""
    now = time.time()
    if now - _status_cache["ts"] > _STATUS_TTL:
        server_reachable, probe_error = await _probe_server()
        _status_cache.update(
            {
                "ts": now,
                "server_reachable": server_reachable,
                "probe_error": probe_error,
            }
        )

    available = sandbox_available()
    server_reachable = bool(_status_cache.get("server_reachable"))
    active = available and server_reachable
    if not available:
        note = "未启用/未安装 opensandbox，回测信号将进程内执行（无容器隔离）"
    elif active:
        note = (
            "opensandbox-server 可达；Docker/镜像最终可用性以首次沙箱创建为准，"
            "失败时自动降级进程内执行"
        )
    else:
        err = _status_cache.get("probe_error") or "server 不可达"
        note = (
            f"opensandbox-server 不可达（{err}）；回测信号将进程内执行"
            "（无容器隔离）"
        )
    return {
        "enabled": settings.sandbox_enabled,
        "package_installed": _pkg_installed(),
        "server_reachable": server_reachable,
        "active": active,
        "image": settings.sandbox_image,
        "note": note,
        "probe_error": _status_cache.get("probe_error", ""),
    }


def _pkg_installed() -> bool:
    try:
        import opensandbox  # noqa: F401
    except Exception:
        return False
    return True
