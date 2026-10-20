"""股票池资格约束 — 逐日 as-of 的 ST/次新/退市整理/板块过滤。

与 `tradable_mask`（停牌、一字板等“当天能不能成交”）分开：
- eligibility=False：不进入股票池、不建仓；已持有的在可成交日退出；
- tradable=False：当天不能成交（停牌/一字），持仓冻结。

所有过滤都按“当日已知信息”判定：
- ST / 退市整理：instrument 名称快照从快照日起前向填充；
- 次新：当日距 list_date 的自然日；
- 北交所：代码后缀。
不会用“今天的 ST/退市状态”倒灌历史截面。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from backend.services import reference_data


class UniversePolicy(BaseModel):
    """一次研究/回测使用的股票池约束。"""

    model_config = ConfigDict(extra="forbid")

    exclude_st: bool = True
    exclude_new: bool = True
    min_list_days: int = Field(default=730, ge=0, le=3650)
    include_bj: bool = True
    exclude_delisting: bool = True

    @classmethod
    def from_settings(cls) -> UniversePolicy:
        from backend.config import settings

        return cls(
            exclude_st=bool(getattr(settings, "universe_exclude_st", True)),
            exclude_new=bool(getattr(settings, "universe_exclude_new", True)),
            min_list_days=int(getattr(settings, "universe_min_list_days", 730)),
            include_bj=bool(getattr(settings, "universe_include_bj", True)),
            exclude_delisting=bool(
                getattr(settings, "universe_exclude_delisting", True)
            ),
        )

    def fingerprint(self) -> str:
        raw = json.dumps(self.model_dump(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def resolve_policy(policy: UniversePolicy | dict | None = None) -> UniversePolicy:
    if policy is None:
        return UniversePolicy.from_settings()
    if isinstance(policy, UniversePolicy):
        return policy
    if isinstance(policy, dict):
        # 空 dict 表示“继承全局默认”，而不是“全用代码默认值”
        return UniversePolicy.from_settings() if not policy else UniversePolicy(**policy)
    raise TypeError(f"不支持的股票池约束类型: {type(policy).__name__}")


@dataclass
class UniverseMaskResult:
    mask: pd.DataFrame
    policy: UniversePolicy
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return self.policy.fingerprint()

    def manifest(self) -> dict:
        return {
            "policy": self.policy.model_dump(),
            "policy_hash": self.fingerprint,
            "stats": self.stats,
            "warnings": list(self.warnings),
        }


def _empty_mask(dates, codes) -> pd.DataFrame:
    return pd.DataFrame(True, index=dates, columns=codes, dtype=bool)


def _snapshot_coverage(dates: pd.DatetimeIndex) -> tuple[str, bool]:
    snap_dates = reference_data.instrument_snapshot_dates()
    if not snap_dates or len(dates) == 0:
        return "", False
    first = pd.Timestamp(snap_dates[0])
    return str(first.date()), first <= dates[0]


def build_equity_eligibility(
    dates,
    codes,
    policy: UniversePolicy | dict | None = None,
) -> UniverseMaskResult:
    """构造逐日股票池资格掩码（True=可进入股票池）。

    Args:
        dates: 日期序列（交易日）
        codes: 股票代码序列
        policy: 约束；None=使用全局配置默认值

    Returns:
        UniverseMaskResult：mask、warnings、按原因统计的剔除计数
    """
    p = resolve_policy(policy)
    idx = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    cols = pd.Index([str(c) for c in codes])
    mask = _empty_mask(idx, cols)
    warnings: list[str] = []
    reason_counts: dict[str, int] = {}
    last_reason_counts: dict[str, int] = {}
    total_cells = int(len(idx) * len(cols))

    def _record(name: str, flags: pd.DataFrame) -> None:
        if flags.empty or not flags.any().any():
            return
        reason_counts[name] = int(flags.to_numpy(dtype=bool).sum())
        last = flags.iloc[-1]
        last_reason_counts[name] = int(last.fillna(False).astype(bool).sum())

    # ── 北交所 ────────────────────────────────────────────
    if not p.include_bj and len(cols):
        bj = pd.Series([str(c).upper().endswith(".BJ") for c in cols], index=cols)
        if bj.any():
            flags = pd.DataFrame(
                np.repeat(bj.to_numpy()[:, None].T, len(idx), axis=0),
                index=idx,
                columns=cols,
            )
            mask &= ~flags
            _record("bj", flags)

    # ── ST / *ST ──────────────────────────────────────────
    st_first = ""
    st_complete = False
    if p.exclude_st:
        st = reference_data.build_st_status(idx, cols)
        if st is None:
            warnings.append("无 instrument 名称快照，ST/*ST 过滤未生效")
        else:
            st_first, st_complete = _snapshot_coverage(idx)
            if st_first and not st_complete:
                warnings.append(
                    f"ST 名称快照自 {st_first} 起覆盖，早于该日的区间无法判定 ST 状态"
                )
            st = st.reindex(index=idx, columns=cols).fillna(False).astype(bool)
            mask &= ~st
            _record("st", st)

    # ── 上市不足 N 天 ─────────────────────────────────────
    list_date_missing = 0
    if p.exclude_new and p.min_list_days > 0:
        inst = reference_data.load_instrument_frame()
        if inst is None or "list_date" not in inst.columns:
            warnings.append("无 instrument 合约快照，次新股过滤未生效")
        else:
            parsed: dict[str, pd.Timestamp] = {}
            for code, raw in inst["list_date"].dropna().items():
                text = str(raw).strip()
                if not text:
                    continue
                try:
                    parsed[str(code)] = pd.Timestamp(text).normalize()
                except Exception:
                    continue
            candidates = [c for c in cols if c in parsed]
            list_date_missing = int(len(cols) - len(candidates))
            if list_date_missing:
                warnings.append(
                    f"{list_date_missing} 只标的缺少上市日，未参与次新过滤"
                )
            if candidates:
                day_arr = idx.values.astype("datetime64[D]")[:, None]
                ld_arr = np.array(
                    [parsed[c].to_datetime64() for c in candidates],
                    dtype="datetime64[D]",
                )[None, :]
                since_days = (day_arr - ld_arr).astype("int64")
                newborn = pd.DataFrame(
                    since_days < int(p.min_list_days),
                    index=idx,
                    columns=candidates,
                ).reindex(index=idx, columns=cols, fill_value=False)
                mask &= ~newborn
                _record("new", newborn)

    # ── 退市整理期（仅按当日名称） ────────────────────────
    if p.exclude_delisting:
        delist = reference_data.build_delisting_status(idx, cols)
        if delist is None:
            warnings.append("无 instrument 名称快照，退市整理期过滤未生效")
        else:
            delist = delist.reindex(index=idx, columns=cols).fillna(False).astype(bool)
            mask &= ~delist
            _record("delisting", delist)

    eligible_cells = int(mask.to_numpy(dtype=bool).sum())
    last_eligible = int(mask.iloc[-1].sum()) if len(mask) else 0
    stats = {
        "n_dates": len(idx),
        "n_codes": len(cols),
        "total_cells": total_cells,
        "eligible_cells": eligible_cells,
        "excluded_cells": total_cells - eligible_cells,
        "excluded_by_reason": reason_counts,
        "excluded_last_date_by_reason": last_reason_counts,
        "eligible_codes_last_date": last_eligible,
        "list_date_missing": list_date_missing,
        "st_snapshot_start": st_first,
        "st_snapshot_complete": bool(st_complete),
        "policy_hash": p.fingerprint(),
    }
    return UniverseMaskResult(mask=mask, policy=p, warnings=warnings, stats=stats)


def apply_policy_to_signals(
    signals: pd.DataFrame,
    policy: UniversePolicy | dict | None = None,
) -> tuple[pd.DataFrame, UniverseMaskResult]:
    """把资格掩码应用到信号面板：不合格标的信号清零（回测引擎会重新归一化）。"""
    result = build_equity_eligibility(signals.index, signals.columns, policy)
    filtered = signals.where(result.mask, 0.0)
    return filtered, result


def apply_policy_to_panels(
    signals: pd.DataFrame,
    prices: pd.DataFrame,
    policy: UniversePolicy | dict | None = None,
) -> tuple[pd.DataFrame, UniverseMaskResult]:
    """以价格面板为基准构建资格掩码，再对齐到信号面板。

    价格面板通常包含完整股票池；信号可能只覆盖部分列。缺失处按可进入处理，
    最终交集仍由回测引擎决定。
    """
    result = build_equity_eligibility(prices.index, prices.columns, policy)
    aligned = result.mask.reindex(index=signals.index, columns=signals.columns)
    filtered = signals.where(aligned.fillna(True), 0.0)
    return filtered, result


def filter_codes_today(
    codes: list[str],
    policy: UniversePolicy | dict | None = None,
) -> tuple[list[str], UniverseMaskResult]:
    """按“今天”的最新快照过滤静态股票列表。

    仅适用于当前选股/下游数据拉取；历史回测应使用逐日 mask，不能拿今天的
    名称状态回溯整段历史。
    """
    p = resolve_policy(policy)
    today = pd.Timestamp.today().normalize()
    result = build_equity_eligibility([today], codes, p)
    if result.mask.empty:
        return list(codes), result
    row = result.mask.iloc[-1]
    kept = [c for c in codes if bool(row.get(c, True))]
    return kept, result
