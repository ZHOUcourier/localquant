"""回测分析服务"""

import numpy as np
import pandas as pd


def _default_equity_codes(market_data) -> list[str]:
    """默认股票池：优先排除指数缓存；兼容测试/插件对 list_cached_codes 的 monkeypatch"""
    try:
        return market_data.list_cached_codes("1d", exclude_indices=True)
    except TypeError:
        return market_data.list_cached_codes("1d")


class BacktestAnalysisService:
    """向量化回测与绩效分析服务"""

    # ── 回测引擎 ─────────────────────────────────────────────

    def run_backtest(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.001,
        slippage: float = 0.001,
        stamp_tax: float = 0.0005,
        normalize: str = "long_only",
        tradable_mask: pd.DataFrame | None = None,
        shortable_mask: pd.DataFrame | None = None,
        up_limit: pd.DataFrame | None = None,
        down_limit: pd.DataFrame | None = None,
        high: pd.DataFrame | None = None,
        low: pd.DataFrame | None = None,
        take_profit: float = 0.0,
        stop_loss: float = 0.0,
        trailing_stop: float = 0.0,
        execute_at: str = "next_close",
        open_prices: pd.DataFrame | None = None,
        delisting_loss: float = 0.0,
        max_gross_exposure: float = 1.0,
    ) -> dict:
        """
        向量化回测（权重空间）。执行口径统一为「T 日信号 → T+1 执行」：
        信号在 T 日收盘算出，于 T+1 成交，自成交时点起计收益；信号当日不产生收益。
        这样可杜绝"用算出信号的那个价格成交"的隐性前视。

        Parameters
        ----------
        signals : DataFrame
            每列为一只标的的信号值（正=买入倾向, 负=不买入, 0=空仓），index 为日期。
        prices : DataFrame
            每列为一只标的的收盘价，index 与 signals 对齐。
        stamp_tax : float
            卖出印花税（买入不收），默认 0.05%。
        normalize : str
            本平台只支持普通股票多头投资：long_only（正信号按日归一，Σw=1，
            总仓位不超过 100%）。负信号一律视为不买入，不融资、不融券、不做空。
        max_gross_exposure : float
            允许的最大日总仓位（Σ|w|）。普通多头默认且上限为 1.0；
            该参数保留为安全护栏，防止未来改动引入意外杠杆。
        tradable_mask : DataFrame | None
            可交易掩码（False=停牌）：停牌日冻结持仓、不计换手成本。
        shortable_mask : DataFrame | None
            兼容旧调用的可融券掩码参数；当前系统只做普通多头，负信号已清零，
            该参数不参与任何交易逻辑。
        up_limit / down_limit / high / low : DataFrame | None
            涨跌停近似价与高低价：一字涨停禁买入加仓、一字跌停禁卖出减仓。
            未成交的调仓意图不推演挂单顺延（持仓保持不动，该笔调仓丢弃），并在
            assumptions 明示次数；缺失时不处理并记入 assumptions。
        take_profit / stop_loss : float（默认 0=关闭）
            单仓止盈 / 止损比例（0.08 = +8% 止盈 / -8% 止损）。基于前收盘判定，T 日执行。
        trailing_stop : float（默认 0=关闭）
            移动止损比例：单仓从建仓后最高点回撤达该比例即止（仅作用于盈利仓 r_prev>=1）。
        execute_at : str
            next_close=T+1 收盘成交（默认）：T 日信号 → T+1 收盘建仓，自 T+1 收盘起
            赚收→收收益（信号当日与建仓当日均不计收益）；
            tail=信号日收盘建仓（尾盘执行）：T 日信号 → T 日收盘建仓，涨跌停/可成交性
            判定取信号日；收益口径与 next_close 一致（持仓前移一期），比 next_close
            早一日建仓；
            next_open=T+1 开盘成交（需 open_prices）：T 日信号 → T+1 开盘建仓，成交日
            新仓按开→收计收益、存量持仓按收→收、卖出部分按隔夜收→开，更贴近打板/
            竞价类策略。
        open_prices : DataFrame | None
            开盘价面板（execute_at=next_open 时使用）。
        delisting_loss : float（默认 0.0）
            数据在回测区间内提前截止的标的（退市或缓存截断）按强制清算处理：
            截止后首个交易日按末日价 ×(1-delisting_loss) 变现并释放权重，不计交易
            费用；delisting_loss=0 表示按末日价全额变现（保守上界）。真实退市损失
            依赖缓存覆盖完整退市整理期价格（可经「退市/历史代码清单」下载）。

        Returns
        -------
        dict 含 strategy_returns / equity_curve / positions / trades / costs /
        assumptions（未能处理的假设清单，报告展示用）/
        delisting_events（强制清算事件清单）。
        """
        # 对齐
        common_idx = signals.index.intersection(prices.index)
        common_cols = signals.columns.intersection(prices.columns)
        signals = signals.loc[common_idx, common_cols]
        prices = prices.loc[common_idx, common_cols]

        assumptions: list[str] = []

        # 收益率：先用最近可用收盘价前向填充再算 pct_change。
        # 原始 pct_change 在停牌/数据缺口处产生 NaN，fillna(0) 会丢失复牌日的
        # 跳空涨跌（停牌期间积累的信息整段消失），系统性低估波动与损失。
        price_returns = prices.ffill().pct_change().fillna(0.0)

        # 数据提前截止检测：每只股票最后一个有效价格日之后的日期标记为「已退市」
        # （数据截止可能是退市，也可能是缓存截断——两种情况都必须强制清算，
        # 否则持仓会以最后价格永久冻结，退市损失与权重泄漏都不被记录）。
        valid_price = prices.notna().to_numpy(dtype=bool)
        n_days, n_assets = valid_price.shape
        last_ok = np.where(
            valid_price.any(axis=0),
            n_days - 1 - np.argmax(valid_price[::-1], axis=0),
            -1,
        )
        day_idx = np.arange(n_days)[:, None]
        dead_arr = day_idx > last_ok[None, :]  # (n_days, n_assets) True=数据已截止

        # 投资边界：普通股票多头，不做空/不加杠杆
        if normalize != "long_only":
            raise ValueError(
                f"不支持 normalize={normalize}。本系统仅支持普通股票多头投资（long_only），"
                "不融资、不融券、不做空；如需调整仓位，请在信号代码中自行转换为正权重。"
            )
        if float(max_gross_exposure) > 1.0:
            raise ValueError(
                "max_gross_exposure 不能超过 1.0：本系统仅支持普通股票多头投资，"
                "任何情况下总仓位都不允许超过 100%。"
            )
        exposure_limit = float(max_gross_exposure)
        weights = self._normalize_weights(signals, normalize)
        gross_before = weights.abs().sum(axis=1).replace(0.0, np.nan)
        gross_max = float(gross_before.max(skipna=True)) if gross_before.notna().any() else 0.0
        if gross_max > exposure_limit + 1e-12:
            worst_ts = gross_before.idxmax(skipna=True)
            raise ValueError(
                f"组合总仓位超过 100%：{gross_max:.2f} > {exposure_limit:.2f}（日期 {worst_ts.date()}）。"
                "本系统仅支持普通股票多头投资，请检查信号是否被正确归一为 long_only 权重。"
            )
        if (signals < 0).to_numpy().any():
            assumptions.append(
                "策略信号中出现负值：已按普通多头规则视为不买入（负信号清零），不做空、不融券"
            )

        # 执行时点：next_close/next_open = T 日信号次日成交（targets 右移一期），
        # tail = 信号日收盘建仓（targets 不移位）；收益统一按「前一日持仓 × 当日涨幅」计
        if execute_at == "tail":
            targets = weights.copy()
            assumptions.append(
                "尾盘执行（tail）：信号日收盘建仓，涨跌停/可成交性判定取信号日；"
                "比 next_close 早一日建仓"
            )
        else:
            targets = weights.shift(1).fillna(0.0)
            if execute_at == "next_open":
                if open_prices is None:
                    assumptions.append(
                        "next_open 执行未提供开盘价面板，按收盘价近似（等价 next_close）"
                    )
                else:
                    open_prices = open_prices.reindex(
                        index=common_idx, columns=common_cols
                    )
            else:
                assumptions.append("T 日信号 T+1 收盘成交（next_close，默认）")

        # 可交易 / 一字板掩码（对齐到回测面板；缺失处理方式记入 assumptions）
        tradable_arr = self._align_mask(
            tradable_mask, common_idx, common_cols, default=True
        )
        if tradable_mask is None:
            assumptions.append("无停牌数据，未处理停牌（停牌日仍可交易）")

        up_board, down_board = self._limit_boards(
            common_idx, common_cols, up_limit, down_limit, high, low, prices
        )
        if up_board is None:
            assumptions.append("无涨跌停/高低价数据，未处理一字板不可成交")
            up_board = np.zeros((len(common_idx), len(common_cols)), dtype=bool)
            down_board = np.zeros_like(up_board)

        # 逐日演进：冻结/顺延/止盈止损等交易规则依赖前一日实际持仓，无法纯 shift 向量化
        tgt_arr = targets.to_numpy(dtype=float)
        pr_arr = price_returns.to_numpy(dtype=float)
        n_days, n_assets = tgt_arr.shape
        pos_arr = np.zeros_like(tgt_arr)
        buy_arr = np.zeros_like(tgt_arr)
        sell_arr = np.zeros_like(tgt_arr)
        prev = np.zeros(n_assets)
        risk_exits = 0
        delisting_pnl = np.zeros(n_days)
        delisting_events: list[dict] = []

        # 风控开启时，逐仓维护「建仓以来累计收益」r_prev 与「持仓期最高」peak_prev
        # （基准 1.0；新建仓当日不计波动，按当日收盘逐日更新 → 按 T-1 收盘判定、T 日执行，
        # 不使用当日盘中价，避免前视）
        manage = bool(take_profit or stop_loss or trailing_stop)
        r_prev = np.ones(n_assets)
        peak_prev = np.ones(n_assets)
        risk_lock = np.zeros(n_assets, dtype=bool)  # True=风控退出后，信号归零前保持空仓
        blocked_trades = 0
        budget_shrink = 0  # 冻结旧仓挤占预算、买入被迫缩减的天数

        for t in range(n_days):
            desired = np.nan_to_num(tgt_arr[t]).copy()

            # 数据已截止的标的（退市/缓存截断）：永不建仓（信号清零，杜绝"死股复活"）
            desired[dead_arr[t]] = 0.0

            # 普通多头边界：负目标权重一律归零（不做空）
            desired[desired < 0] = 0.0

            # 风控锁：退出后保持空仓，直到策略自身信号归零才允许日后重新开仓
            if manage:
                risk_lock[np.abs(tgt_arr[t]) <= 1e-12] = False
                if risk_lock.any():
                    desired[risk_lock] = 0.0

            # 止盈 / 止损 / 移动止损（用截至 t-1 收盘的持仓收益判定，T 日执行；
            # 多头按 price_ret 计盈，空头按 -price_ret 计盈，长/空两侧同套风控）
            if manage and t > 0:
                trig = np.zeros(n_assets, dtype=bool)
                if stop_loss > 0:
                    trig |= r_prev - 1 <= -stop_loss
                if take_profit > 0:
                    trig |= r_prev - 1 >= take_profit
                if trailing_stop > 0:
                    trig |= (peak_prev - r_prev >= trailing_stop) & (r_prev >= 1)
                exit_now = trig & (prev != 0.0)
                if exit_now.any():
                    desired[exit_now] = 0.0
                    risk_lock[exit_now] = True
                    risk_exits += int(exit_now.sum())

            actual = desired.copy()
            was_held = prev != 0.0
            frozen = ~tradable_arr[t]
            actual[frozen] = prev[frozen]
            buy_blocked = up_board[t] & (desired > prev)
            actual[buy_blocked] = prev[buy_blocked]
            sell_blocked = down_board[t] & (desired < prev)
            actual[sell_blocked] = prev[sell_blocked]
            # 数据截止（退市/缓存截断）：截止后首个交易日强制清算，
            # 按末日价 ×(1-delisting_loss) 变现，不计交易费用（非市场交易）
            forced = dead_arr[t]
            if forced.any():
                forced_held = forced & was_held
                if forced_held.any():
                    loss_rate = float(delisting_loss)
                    delisting_pnl[t] = -loss_rate * float(prev[forced_held].sum())
                    for c_idx in np.nonzero(forced_held)[0]:
                        delisting_events.append(
                            {
                                "date": str(pd.Timestamp(common_idx[t]).date()),
                                "code": str(common_cols[c_idx]),
                                "weight": float(prev[c_idx]),
                                "loss_rate": loss_rate,
                            }
                        )
                actual[forced] = 0.0
            if (buy_blocked | sell_blocked).any():
                blocked_trades += int((buy_blocked | sell_blocked).sum())
            # 总仓位硬约束：冻结/一字板/清算后若 Σ|w| 仍超限（旧仓卖不出、买入侧又按计划
            # 全额成交所致），只等比缩减买入增量至预算内；卖出与冻结仓位不动。
            # 保证任何情况下 Σ|w| ≤ exposure_limit（普通多头不加杠杆、不融资）。
            gross_now = float(actual.sum())  # long_only 权重全非负
            if gross_now > exposure_limit + 1e-12:
                excess = gross_now - exposure_limit
                buy_inc = np.maximum(actual - prev, 0.0)
                total_buy = float(buy_inc.sum())
                if total_buy > 1e-15:
                    scale = max(0.0, 1.0 - excess / total_buy)
                    buying = actual > prev
                    actual[buying] = (
                        prev[buying] + (actual[buying] - prev[buying]) * scale
                    )
                    budget_shrink += 1
            trade = actual - prev
            # 强制清算不是市场交易：不计入换手与成本（损失已由 delisting_pnl 单独入账）
            trade[dead_arr[t]] = 0.0
            buy_arr[t] = np.clip(trade, 0.0, None)
            sell_arr[t] = np.clip(-trade, 0.0, None)
            pos_arr[t] = actual
            prev = actual

            # 收盘后更新持仓收益轨迹（符号感知：多头× 价涨利润，空头×价跌）
            # 新建仓当日（T+1 才成交）尚无持仓收益，r_prev 重置为基准 1.0，
            # 自次日起逐日累计 —— 避免把建仓当日波动计入而提前触发止盈/止损
            if manage:
                sign_prev = np.where(prev > 0, 1.0, np.where(prev < 0, -1.0, 0.0))
                hold_after = actual != 0.0
                same_side = np.where(actual * prev > 0, True, False)
                pnl = (1.0 + sign_prev * np.nan_to_num(pr_arr[t]))
                r_prev = np.where(
                    hold_after & was_held & same_side,
                    r_prev * pnl,
                    np.where(
                        hold_after,
                        1.0,
                        r_prev,
                    ),
                )
                # 移动止损：持仓期间累计最高点（含新建仓首日，确保重仓时峰值清零）
                peak_prev = np.where(
                    hold_after,
                    np.where(
                        was_held & same_side,
                        np.maximum(peak_prev, r_prev),
                        r_prev,
                    ),
                    peak_prev,
                )

        # 一字板/停牌导致调仓未能成交：持仓保持，未成交意图不追单（如实记录，不改写价格）
        if blocked_trades:
            assumptions.append(
                f"涨停/跌停一字板共 {int(blocked_trades)} 次调仓无法按计划成交，"
                f"当期持仓保持不动、该笔调仓意图不保留（不做挂单顺延推演）"
            )

        if budget_shrink:
            assumptions.append(
                f"共 {budget_shrink} 个交易日因冻结旧仓（停牌/一字跌停）挤占预算，"
                f"买入权重被等比缩减以守住 {exposure_limit:.0%} 总仓位上限"
                "（不追单、不加杠杆，未成交部分如实放弃）"
            )

        n_dead = int(dead_arr.any(axis=0).sum())
        if n_dead:
            held_dead = sum(1 for e in delisting_events if e["weight"] != 0.0)
            assumptions.append(
                f"{n_dead} 只股票数据在回测区间内提前截止（退市或缓存截断）："
                f"截止后首日按末日价 ×(1-{float(delisting_loss):.0%}) 强制清算"
                f"（{held_dead} 只有实际持仓被清算，不计交易费用），"
                "剩余未实现退市损失风险由该假设承担 — 请用「退市/历史代码清单」"
                "补齐退市整理期行情使损失如实入账"
            )

        if manage:
            notes = []
            if stop_loss > 0:
                notes.append(f"止损 {stop_loss:.1%}")
            if take_profit > 0:
                notes.append(f"止盈 {take_profit:.1%}")
            if trailing_stop:
                notes.append(f"移动止损 {trailing_stop:.1%}")
            assumptions.append(
                "逐仓风控(" + "/".join(notes) + ")：按 T-1 收盘判定、T 日执行，共触发 "
                + str(risk_exits)
                + " 次卖出；持仓收益按复利近似（连续再平衡下为近似），不影响 T+1 语义"
            )

        positions = pd.DataFrame(pos_arr, index=common_idx, columns=common_cols)
        trades = pd.DataFrame(buy_arr + sell_arr, index=common_idx, columns=common_cols)

        # 仓位边界不变量：预算约束后任何交易日都应满足 Σ|w| ≤ exposure_limit，
        # 一旦越界说明引擎逻辑有缺陷 —— 视为错误抛出，而不是输出带杠杆的结果
        gross_check = positions.abs().sum(axis=1)
        over = gross_check[gross_check > exposure_limit + 1e-9]
        if len(over):
            worst = over.idxmax()
            raise RuntimeError(
                f"回测引擎内部错误：{worst.date()} 总仓位 {float(over[worst]):.6f} "
                f"超过上限 {exposure_limit:.2f}。预算约束应已消除越界，请报告复现场景。"
            )

        # 成本拆分：佣金（买卖双向）/ 滑点（买卖双向）/ 印花税（仅卖出）
        # 与原合并口径完全一致：buy×(c+s) + sell×(c+s+t) = (buy+sell)×c + (buy+sell)×s + sell×t
        turnover_series = trades.sum(axis=1)
        commission_costs = turnover_series * commission_rate
        slippage_costs = turnover_series * slippage
        stamp_costs = pd.Series(sell_arr.sum(axis=1), index=common_idx) * stamp_tax
        costs = commission_costs + slippage_costs + stamp_costs

        cost_summary = self._cost_breakdown(
            costs, commission_costs, slippage_costs, stamp_costs, turnover_series
        )

        # 策略日收益：positions[t] 为成交日持仓；第 t 日收益 = positions[t-1] × 第 t 日涨幅
        # − 第 t 日交易成本（T 日信号 → T+1 成交，最早赚 T+1 收盘→T+2 收盘的涨幅，无前视）
        # 强制清算损失 delisting_pnl 计入清算当日（末日价 ×(1-loss) 变现于当日收盘）
        held_prev = positions.shift(1).fillna(0.0)
        if execute_at == "next_open" and open_prices is not None:
            # T+1 开盘成交：三段归属 —— 存量持仓赚收→收、新买部分赚开→收、
            # 卖出部分赚隔夜收→开（持有到开盘卖出），避免整仓误用开盘收益
            op = open_prices.reindex(index=common_idx, columns=common_cols)
            ret_oc = (prices / op.replace(0, np.nan) - 1.0).fillna(0.0)
            ret_co = (op / prices.shift(1).replace(0, np.nan) - 1.0).fillna(0.0)
            pos_prev_arr = held_prev.to_numpy()
            pos_curr_arr = positions.to_numpy()
            held_arr = np.minimum(pos_prev_arr, pos_curr_arr)
            strategy_returns = (
                pd.Series(
                    (held_arr * pr_arr).sum(axis=1)
                    + ((pos_curr_arr - held_arr) * ret_oc.to_numpy()).sum(axis=1)
                    + ((pos_prev_arr - held_arr) * ret_co.to_numpy()).sum(axis=1),
                    index=common_idx,
                )
                - costs
                + pd.Series(delisting_pnl, index=common_idx)
            )
        else:
            # next_close（默认）/ tail：当日收益 = 前一日持仓 × 当日收→收涨幅
            strategy_returns = (
                (held_prev * price_returns).sum(axis=1)
                - costs
                + pd.Series(delisting_pnl, index=common_idx)
            )

        # 净值曲线
        equity_curve = (1 + strategy_returns).cumprod() * initial_capital

        # 杠杆与破产边界：显式报告，而不是让负净值静默继续复利
        gross_series = positions.abs().sum(axis=1)
        net_series = positions.sum(axis=1)
        leverage_summary = {
            "max_gross_exposure": float(gross_series.max()),
            "mean_gross_exposure": float(gross_series.mean()),
            "max_net_exposure": float(net_series.max()),
            "min_net_exposure": float(net_series.min()),
            "gross_exposure_limit": float(max_gross_exposure),
            "budget_shrink_days": int(budget_shrink),
        }
        min_equity = float(equity_curve.min())
        if min_equity <= 0:
            ruined = equity_curve[equity_curve <= 0]
            ruin_date = str(ruined.index[0].date()) if len(ruined) else None
            leverage_summary["ruin_date"] = ruin_date
            leverage_summary["min_equity"] = min_equity
            assumptions.append(
                f"组合净值在 {ruin_date} 触及或跌破 0（最低 {min_equity:.2f}）；"
                "负净值后的复利结果无经济意义，请检查成本与数据口径"
            )

        return {
            "strategy_returns": strategy_returns,
            "equity_curve": equity_curve,
            "positions": positions,
            "trades": trades,
            "costs": costs,
            "commission_costs": commission_costs,
            "slippage_costs": slippage_costs,
            "stamp_costs": stamp_costs,
            "cost_summary": cost_summary,
            "assumptions": assumptions,
            "delisting_events": delisting_events,
            "delisting_pnl": pd.Series(delisting_pnl, index=common_idx),
            "initial_capital": initial_capital,
            "leverage_summary": leverage_summary,
            "gross_exposure": gross_series,
            "net_exposure": net_series,
        }

    @staticmethod
    def _normalize_weights(signals: pd.DataFrame, method: str) -> pd.DataFrame:
        """按日截面归一信号为权重（仅普通多头）"""
        if method != "long_only":
            raise ValueError(
                f"不支持 normalize={method}。本系统仅支持普通股票多头投资（long_only），"
                "不融资、不融券、不做空。"
            )
        w = signals.clip(lower=0.0)
        row_sum = w.sum(axis=1)
        return w.div(row_sum.where(row_sum > 0, np.nan), axis=0).fillna(0.0)

    @staticmethod
    def _align_mask(
        mask: pd.DataFrame | None,
        idx: pd.Index,
        cols: pd.Index,
        default: bool,
    ) -> np.ndarray:
        """将布尔掩码对齐到回测面板，缺失处用 default 填充"""
        if mask is None:
            return np.full((len(idx), len(cols)), default, dtype=bool)
        aligned = mask.reindex(index=idx, columns=cols)
        return aligned.fillna(default).to_numpy(dtype=bool)

    @staticmethod
    def _limit_boards(
        idx: pd.Index,
        cols: pd.Index,
        up_limit: pd.DataFrame | None,
        down_limit: pd.DataFrame | None,
        high: pd.DataFrame | None,
        low: pd.DataFrame | None,
        close: pd.DataFrame,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """一字板判定：high==low 且收盘触及涨/跌停近似价；数据不全返回 None"""
        if up_limit is None or down_limit is None or high is None or low is None:
            return None, None
        h = high.reindex(index=idx, columns=cols)
        low_ = low.reindex(index=idx, columns=cols)
        up = up_limit.reindex(index=idx, columns=cols)
        dn = down_limit.reindex(index=idx, columns=cols)
        c = close.reindex(index=idx, columns=cols)
        one_line = (h - low_).abs() < 1e-9
        up_board = (one_line & (c >= up - 0.005)).fillna(False).to_numpy(dtype=bool)
        down_board = (one_line & (c <= dn + 0.005)).fillna(False).to_numpy(dtype=bool)
        return up_board, down_board

    # ── 成本拆分报告 ─────────────────────────────────────────

    @staticmethod
    def _cost_breakdown(
        costs: "pd.Series",
        commission: "pd.Series",
        slippage: "pd.Series",
        stamp: "pd.Series",
        turnover: "pd.Series",
    ) -> dict:
        """成本构成汇总：佣金/滑点/印花税分列（金额、占比、每单位换手的 bps 成本）"""
        total = float(costs.sum())
        totals = {
            "commission": float(commission.sum()),
            "slippage": float(slippage.sum()),
            "stamp_tax": float(stamp.sum()),
        }
        total_turnover = float(turnover.sum())
        return {
            "total_cost": total,
            "breakdown": totals,
            "shares": {
                k: (v / total if total > 0 else 0.0) for k, v in totals.items()
            },
            "cost_bps_per_turnover": (total / total_turnover * 1e4)
            if total_turnover > 0
            else 0.0,
            "total_turnover": total_turnover,
            "n_days": int(costs.dropna().size),
        }

    # ── 容量分析 ─────────────────────────────────────────────

    def capacity_analysis(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        amount: pd.DataFrame | None = None,
        normalize: str = "long_only",
        participation_rate: float = 0.1,
        capital_levels: list[float] | None = None,
        adv_window: int = 20,
        lot_size: int = 100,
    ) -> dict:
        """容量分析：信号在给定参与率约束下可容纳的资金规模

        思路（与回测引擎同一套 T+1 权重语义）：
        - 目标权重按日截面归一 → T+1 执行，日换手金额 = |Δw| × 资金规模；
        - 每只标的日成交额占比 = 换手金额 / 滚动 20 日平均成交额（ADV）；
        - 超参与率约束（如 10%）即认为冲击不可忽略。

        Returns:
            levels: 各资金规模下的受限指标；suggested_capacity: 保证任何
            (日, 标的) 换手占比都不超参与率的理论容量上限。
        """
        assumptions: list[str] = []
        if amount is None:
            return {
                "ok": False,
                "message": "缺少成交额面板（amount），容量分析需要每只标的的日成交额",
                "levels": [],
                "suggested_capacity": 0.0,
                "assumptions": ["无成交额数据，容量分析不可用"],
            }

        common_idx = signals.index.intersection(prices.index)
        common_cols = signals.columns.intersection(prices.columns)
        signals = signals.loc[common_idx, common_cols]
        prices = prices.loc[common_idx, common_cols]
        amount = amount.reindex(index=common_idx, columns=common_cols)

        if amount.isna().all().all():
            return {
                "ok": False,
                "message": "成交额面板全为空，容量分析不可用",
                "levels": [],
                "suggested_capacity": 0.0,
                "assumptions": ["成交额面板全为空"],
            }

        # 与回测一致的权重归一 + T+1 执行
        weights = self._normalize_weights(signals, normalize)
        targets = weights.shift(1).fillna(0.0)
        turnover = targets.diff().abs().fillna(0.0)  # |Δw|（首日按建仓）

        # 滚动平均成交额（ADV，单位元）；窗口可调，样本不足时用较短窗口
        adv = amount.rolling(adv_window, min_periods=max(5, adv_window // 4)).mean()

        levels_out: list[dict] = []
        for cap in capital_levels or [1e8, 5e8, 1e9, 5e9, 1e10]:
            traded_value = turnover * cap  # (日, 标的) 换手金额
            participation = traded_value / adv.replace(0, float("nan"))
            share = (participation > participation_rate).fillna(False)
            valid = participation.notna() & (turnover > 0)
            exceed_days = share.sum(axis=0)
            exceed_ratio_days = float(
                (share.any(axis=1)).mean() if len(share) else 0.0
            )
            constrained_stocks = int((exceed_days > 0).sum())
            # 布尔 DataFrame 索引会保留原形状并把无效位置填 NaN（pandas 语义），
            # 必须先取出 numpy 掩码再取值，否则 mean 恒为 NaN。
            pvals = (
                participation.to_numpy()[valid.to_numpy()]
                if valid.any().any()
                else None
            )
            pvals = pvals[np.isfinite(pvals)] if pvals is not None else None
            mean_participation = (
                float(pvals.mean()) if pvals is not None and pvals.size else 0.0
            )
            p95 = (
                float(np.nanpercentile(pvals, 95))
                if pvals is not None and pvals.size
                else 0.0
            )
            levels_out.append(
                {
                    "capital": cap,
                    "exceed_days_ratio": round(exceed_ratio_days, 4),
                    "mean_participation": round(mean_participation, 4),
                    "p95_participation": round(p95, 4),
                    "constrained_stocks": constrained_stocks,
                    "tradable_ratio": round(
                        float((turnover > 0).any(axis=1).mean()), 4
                    )
                    if len(turnover)
                    else 0.0,
                }
            )

        # 理论容量：基准规模下最大单笔参与率 → 反推
        base_cap = 1e8
        traded_base = turnover * base_cap
        participation_base = traded_base / adv.replace(0, float("nan"))
        pvals_base = (
            participation_base.to_numpy()[valid.to_numpy()]
            if valid.any().any()
            else None
        )
        pvals_base = (
            pvals_base[np.isfinite(pvals_base)] if pvals_base is not None else None
        )
        max_ratio = (
            float(pvals_base.max())
            if pvals_base is not None and pvals_base.size
            else 0.0
        )
        # max_ratio=0 意味着基准确样本无流动性约束（如极低换手），给一个名义上限（1000 亿）
        suggested = (
            base_cap * participation_rate / max_ratio
            if max_ratio > 0
            else 1e11
        )

        assumptions.append(
            f"容量分析按参与率 ≤ {participation_rate:.0%} 约束，ADV 取滚动 {adv_window} 日均值；"
            f"A 股按 {lot_size} 股/手整手交易假设，未模拟涨跌停不可成交、"
            "冲击成本非线性、订单簿深度与下单算法执行细节"
        )
        return {
            "ok": True,
            "participation_rate": participation_rate,
            "adv_window": int(adv_window),
            "lot_size": int(lot_size),
            "levels": levels_out,
            "suggested_capacity": float(suggested),
            "suggested_label": self._format_capital(float(suggested)),
            "assumptions": assumptions,
        }

    @staticmethod
    def _format_capital(value: float) -> str:
        """资金规模友好格式化：1.0 亿 / 5000 万 / 1000 万"""
        if value >= 1e8:
            return f"{value / 1e8:.1f} 亿"
        if value >= 1e4:
            return f"{value / 1e4:.0f} 万"
        return f"{value:.0f} 元"

    # ── 因子池 → 组合回测闭环 ─────────────────────────────────

    def portfolio_backtest(
        self,
        factors: list[dict],
        stock_pool: list[str] | None = None,
        start_date: str = "",
        end_date: str = "",
        combine_method: str = "equal",
        top_n: int = 20,
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.001,
        slippage: float = 0.001,
        stamp_tax: float = 0.0005,
        take_profit: float = 0.0,
        stop_loss: float = 0.0,
        trailing_stop: float = 0.0,
        execute_at: str = "next_close",
        delisting_loss: float = 0.0,
    ) -> dict:
        """因子池 → 组合回测闭环（研究主链路一键打通）

        因子公式求值（本地面板，一次加载）→ 合成（等权/IC 加权）→
        每日截面取 Top-N 做多 → 向量化回测 → 绩效 → 风格归因。

        Args:
            factors: [{factor_id, factor_name, formula}]
            combine_method: equal=等权合成 / ic_weighted=按滚动 RankIC 逐日加权
                （样本外口径：T 日权重只用 T 之前 120 日的信息，无前视；
                早期窗口不足的截面不建仓）
            top_n: 每期截面做多只数（0=全部正因子值做多）

        Returns:
            {ok, message, signals?, equity_curve, strategy_returns,
             tear_sheet, cost_summary, attribution, factor_weights, failed}
        """
        from backend.services import market_data, reference_data, risk
        from backend.services.factor_operators import (
            build_operator_namespace,
            eval_factor_formula,
        )
        from backend.services.factor_research import factor_research

        codes = stock_pool or _default_equity_codes(market_data)
        if len(codes) < 30:
            raise ValueError(
                f"本地仅 {len(codes)} 只股票缓存，不足以构建组合（至少 30 只）— "
                "请先在「数据中心」下载行情数据"
            )
        panels = market_data.load_price_panels(
            codes=codes, start_date=start_date, end_date=end_date
        )
        close = panels["close"]
        if close is None or len(close.index) < 60:
            raise ValueError("行情区间不足 60 个交易日，无法回测")

        ns = build_operator_namespace(
            panels, industry_map=reference_data.load_industry_map()
        )
        factor_frames: dict[str, pd.DataFrame] = {}
        failed: list[dict] = []
        for f in factors:
            try:
                fd = eval_factor_formula(f["formula"], ns)
                if isinstance(fd, pd.Series):
                    fd = fd.to_frame()
                if isinstance(fd, pd.DataFrame) and not fd.empty:
                    factor_frames[f["factor_name"]] = fd.reindex(index=close.index)
                else:
                    failed.append({"factor_name": f["factor_name"], "error": "公式未产出有效面板"})
            except Exception as e:
                failed.append({"factor_name": f["factor_name"], "error": str(e)[:200]})
        if not factor_frames:
            raise ValueError(
                "所选因子均无法求值（" + "；".join(f"{x['factor_name']}: {x['error']}" for x in failed[:3]) + "）"
            )

        return_data = market_data.build_return_panel(close)
        combined: pd.DataFrame
        weights: dict[str, float] | None = None
        weight_series: dict[str, pd.Series] | None = None
        if combine_method == "ic_weighted" and len(factor_frames) >= 2:
            # 样本外口径：T 日权重只用 (T-window, T] 的 RankIC（滚动、无前视）。
            # 早期窗口不足的截面权重为 NaN → 信号 NaN，回测引擎按 0 权重处理（不建仓）。
            weight_series, _ = factor_research._rolling_ic_weights(
                factor_frames, return_data, ic_window=120, min_window=20
            )
            frames = {n: f.reindex(close.index) for n, f in factor_frames.items()}
            wdf = pd.DataFrame(weight_series).sort_index()
            # 逐日截面 z-score 后按当日权重合成
            zframes = {}
            for n, f in frames.items():
                z = (f - f.mean(axis=1)) / f.std(axis=1).replace(0, np.nan)
                zframes[n] = z
            parts = []
            for n, zframe in zframes.items():
                w_n = wdf[n] if n in wdf.columns else pd.Series(0.0, index=close.index)
                parts.append(zframe.mul(w_n.reindex(zframe.index), axis=0))
            combined = pd.concat(parts).groupby(level=0).sum().reindex(close.index)
            weights = {
                n: float(v.abs().mean()) for n, v in wdf.items() if n in factor_frames
            }
        else:
            combined = factor_research.multi_factor_combine(factor_frames, method="equal")
            weights = {k: 1.0 / len(factor_frames) for k in factor_frames}

        # 每日截面 Top-N 做多信号（T 日信号 → 回测引擎 T+1 执行）
        n = int(top_n)
        if n <= 0:
            signals = (combined > 0).astype(float)
        else:
            ranked = combined.rank(axis=1, ascending=False)
            signals = pd.DataFrame(
                0.0, index=combined.index, columns=combined.columns
            )
            signals[ranked <= n] = 1.0
        signals = signals.fillna(0.0)

        reference = market_data.load_reference_panels(close, panels.get("volume"))
        # 普通股票多头：组合回测只做多，不加载/不使用两融池做空掩码。
        result = self.run_backtest(
            signals=signals,
            prices=close,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage=slippage,
            stamp_tax=stamp_tax,
            normalize="long_only",
            tradable_mask=reference["tradable_mask"],
            shortable_mask=None,
            up_limit=reference["up_limit"],
            down_limit=reference["down_limit"],
            high=panels.get("high"),
            low=panels.get("low"),
            take_profit=take_profit,
            stop_loss=stop_loss,
            trailing_stop=trailing_stop,
            execute_at=execute_at,
            open_prices=panels.get("open") if execute_at == "next_open" else None,
            delisting_loss=delisting_loss,
        )
        strategy_returns = result["strategy_returns"]
        tear = self.performance_tear_sheet(returns=strategy_returns)
        dd = self.drawdown_analysis(strategy_returns)

        # 风格归因（失败不阻断主结果）
        attribution: dict | None = None
        try:
            styles = risk.build_style_exposures(
                close, volume=panels.get("volume"), amount=panels.get("amount")
            )
            style_res = risk.style_factor_returns(return_data, styles)
            attr = risk.strategy_regression_attribution(
                strategy_returns, style_res["factor_returns"]
            )
            if attr.get("ok"):
                attribution = {
                    "alpha_cum": attr["alpha_cum"],
                    "alpha_annual": attr["alpha_annual"],
                    "alpha_ir": attr["alpha_ir"],
                    "r2": attr["r2"],
                    "beta": attr["beta"],
                    "contribution": attr["contribution"],
                    "n_obs": attr["n_obs"],
                }
        except Exception:
            attribution = None

        return {
            "ok": True,
            "combine_method": combine_method,
            "top_n": n,
            "n_factors": len(factor_frames),
            "factor_names": list(factor_frames.keys()),
            "factor_weights": weights or {k: 1.0 / len(factor_frames) for k in factor_frames},
            "weight_method": (
                "样本外滚动加权（T 日权重仅用 T 之前 120 日 RankIC）"
                if combine_method == "ic_weighted"
                else "等权"
            ),
            "failed": failed,
            "equity_curve": {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in result["equity_curve"].items()
            },
            "strategy_returns": {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in strategy_returns.items()
            },
            "drawdown_series": {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in dd["drawdown_series"].items()
            },
            "tear_sheet": {**tear, "max_drawdown": dd["max_drawdown"]},
            "cost_summary": result["cost_summary"],
            "attribution": attribution,
            "assumptions": result["assumptions"],
            "delisting_events": result.get("delisting_events", []),
            "n_stocks": int(close.shape[1]),
            "data_date": str(close.index[-1])[:10],
        }

    # ── 组合 walk-forward 回测（滚动拼接净值，防过拟合最后一环）────────────


    def walk_forward_portfolio(
        self,
        factors: list[dict],
        stock_pool: list[str] | None = None,
        start_date: str = "",
        end_date: str = "",
        combine_method: str = "equal",
        top_n: int = 20,
        train_days: int = 120,
        test_days: int = 60,
        initial_capital: float = 1_000_000,
        commission_rate: float = 0.001,
        slippage: float = 0.001,
        stamp_tax: float = 0.0005,
        take_profit: float = 0.0,
        stop_loss: float = 0.0,
        trailing_stop: float = 0.0,
        execute_at: str = "next_close",
        delisting_loss: float = 0.0,
    ) -> dict:
        """组合 walk-forward 回测：训练窗口定权重 → 测试窗口出信号 → 滚动拼接净值

        与 factor_research.walk_forward_validation（只验 IC）互补：这里是完整的
        「滚动调参 → 组合回测 → 拼接净值」闭环，直接回答「参数在样本外是否稳健」。

        - 测试窗口不重叠、逐折后移（滚动锚定：训练集始终从样本起点开始）；
        - ic_weighted 时每折权重只用该折训练集（<= train_end）的 RankIC，无前视；
        - 训练窗口内不建仓（信号置 0），净值只覆盖样本外测试段；
        - 另附「全样本参考」净值（同一信号不遮罩训练段）作对比，直观展示过拟合差距。

        Returns:
            {ok, folds, equity_curve, strategy_returns, tear_sheet,
             drawdown, assumptions, in_sample_reference, failed}
        """
        from backend.services import market_data, reference_data
        from backend.services.factor_operators import (
            build_operator_namespace,
            eval_factor_formula,
        )
        from backend.services.factor_research import factor_research

        codes = stock_pool or _default_equity_codes(market_data)
        if len(codes) < 30:
            raise ValueError(
                f"本地仅 {len(codes)} 只股票缓存，不足以构建组合（至少 30 只）— "
                "请先在「数据中心」下载行情数据"
            )
        panels = market_data.load_price_panels(
            codes=codes, start_date=start_date, end_date=end_date
        )
        close = panels["close"]
        if close is None or len(close.index) < train_days + test_days + 30:
            raise ValueError("行情区间不足（需 ≥ 训练窗口 + 测试窗口 + 30 个交易日）")

        ns = build_operator_namespace(
            panels, industry_map=reference_data.load_industry_map()
        )
        factor_frames: dict[str, pd.DataFrame] = {}
        failed: list[dict] = []
        for f in factors:
            try:
                fd = eval_factor_formula(f["formula"], ns)
                if isinstance(fd, pd.Series):
                    fd = fd.to_frame()
                if isinstance(fd, pd.DataFrame) and not fd.empty:
                    factor_frames[f["factor_name"]] = fd.reindex(index=close.index)
                else:
                    failed.append({"factor_name": f["factor_name"], "error": "公式未产出有效面板"})
            except Exception as e:
                failed.append({"factor_name": f["factor_name"], "error": str(e)[:200]})
        if not factor_frames:
            raise ValueError(
                "所选因子均无法求值（" + "；".join(f"{x['factor_name']}: {x['error']}" for x in failed[:3]) + "）"
            )

        return_data = market_data.build_return_panel(close)
        dates = close.index
        n = len(dates)

        def _top_n_signal(combined: pd.DataFrame) -> pd.DataFrame:
            tn = int(top_n)
            if tn <= 0:
                return (combined > 0).astype(float)
            ranked = combined.rank(axis=1, ascending=False)
            sig = pd.DataFrame(0.0, index=combined.index, columns=combined.columns)
            sig[ranked <= tn] = 1.0
            return sig.fillna(0.0)

        folds: list[dict] = []
        t = 0
        signals_oos = pd.DataFrame(
            0.0, index=dates, columns=close.columns
        )
        while t + train_days + test_days <= n:
            train_end = dates[t + train_days - 1]
            test_start = dates[t + train_days]
            test_end = dates[min(t + train_days + test_days - 1, n - 1)]
            if combine_method == "ic_weighted" and len(factor_frames) >= 2:
                w = factor_research._ic_weights(
                    factor_frames, return_data, ic_window=train_days, as_of=train_end
                )
                combined = factor_research.multi_factor_combine(factor_frames, weights=w)
            else:
                combined = factor_research.multi_factor_combine(
                    factor_frames, method="equal"
                )
            sig_fold = _top_n_signal(combined)
            mask = (dates >= test_start) & (dates <= test_end)
            signals_oos.loc[mask] = sig_fold.loc[mask]
            folds.append(
                {
                    "fold": len(folds) + 1,
                    "train_start": str(dates[0].date()),
                    "train_end": str(train_end.date()),
                    "test_start": str(test_start.date()),
                    "test_end": str(test_end.date()),
                }
            )
            t += test_days

        if not folds:
            raise ValueError("窗口划分失败：训练+测试窗口超出数据区间")

        # 全样本参考信号：同一合成逻辑覆盖全部区间（含训练段，可交易性不计）——
        # 与样本外净值对照，直观展示「参数在训练段内拟合出的虚高」差距
        if combine_method == "ic_weighted" and len(factor_frames) >= 2:
            combined_full = factor_research.multi_factor_combine(
                factor_frames,
                weights=factor_research._ic_weights(
                    factor_frames, return_data, ic_window=train_days
                ),
            )
        else:
            combined_full = factor_research.multi_factor_combine(
                factor_frames, method="equal"
            )
        signals_full = _top_n_signal(combined_full)

        reference = market_data.load_reference_panels(close, panels.get("volume"))
        common_kwargs = {
            "prices": close,
            "initial_capital": initial_capital,
            "commission_rate": commission_rate,
            "slippage": slippage,
            "stamp_tax": stamp_tax,
            "normalize": "long_only",
            "tradable_mask": reference["tradable_mask"],
            "up_limit": reference["up_limit"],
            "down_limit": reference["down_limit"],
            "high": panels.get("high"),
            "low": panels.get("low"),
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "trailing_stop": trailing_stop,
            "execute_at": execute_at,
            "open_prices": panels.get("open") if execute_at == "next_open" else None,
            "delisting_loss": delisting_loss,
        }
        res = self.run_backtest(signals=signals_oos, **common_kwargs)
        res_full = self.run_backtest(signals=signals_full, **common_kwargs)

        returns = res["strategy_returns"]
        tear = self.performance_tear_sheet(returns=returns)
        dd = self.drawdown_analysis(returns)
        tear_full = self.performance_tear_sheet(returns=res_full["strategy_returns"])

        return {
            "ok": True,
            "n_folds": len(folds),
            "folds": folds,
            "combine_method": combine_method,
            "top_n": int(top_n),
            "n_factors": len(factor_frames),
            "factor_names": list(factor_frames.keys()),
            "failed": failed,
            "equity_curve": {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in res["equity_curve"].items()
            },
            "strategy_returns": {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in returns.items()
            },
            "drawdown_series": {
                str(k.date() if hasattr(k, "date") else k): float(v)
                for k, v in dd["drawdown_series"].items()
            },
            "tear_sheet": {**tear, "max_drawdown": dd["max_drawdown"]},
            "in_sample_reference": {
                "total_return": tear_full.get("total_return"),
                "annual_return": tear_full.get("annual_return"),
                "sharpe_ratio": tear_full.get("sharpe_ratio"),
                "max_drawdown": tear_full.get("max_drawdown"),
                "trading_days": tear_full.get("trading_days"),
                "note": (
                    "全样本参考：同一合成逻辑覆盖全部区间（含训练段建仓，非可交易结果），"
                    "用于对比展示训练段内的拟合虚高"
                ),
            },
            "assumptions": res["assumptions"]
            + [
                (
                    "样本外净值仅覆盖各折测试段；训练窗口内不建仓；"
                    "ic_weighted 时权重只含训练窗口 RankIC，无前视"
                ),
            ],
            "n_stocks": int(close.shape[1]),
            "data_date": str(close.index[-1])[:10],
        }

    # ── 回测参数敏感性（网格扫描）────────────────────────────
    def sensitivity_scan(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        param_grid: dict[str, list],
        base: dict | None = None,
        tradable_mask=None,
        up_limit=None,
        down_limit=None,
        high=None,
        low=None,
    ) -> dict:
        """回测参数网格扫描：对 param_grid 做笛卡尔积，逐组合跑回测

        信号只算一次、面板共享；返回每个组合的绩效对比表，供研究员
        验证策略对参数（成本/止盈止损/滑点等）的稳健性。

        param_grid 支持键：commission_rate / slippage / stamp_tax /
        normalize / take_profit / stop_loss / trailing_stop
        """
        import itertools

        base = base or {}
        keys = list(param_grid.keys())
        combos = list(itertools.product(*param_grid.values()))
        rows: list[dict] = []
        for combo in combos:
            params = dict(base)
            params.update(dict(zip(keys, combo)))
            try:
                result = self.run_backtest(
                    signals=signals,
                    prices=prices,
                    initial_capital=float(params.get("initial_capital", 1_000_000)),
                    commission_rate=float(params.get("commission_rate", 0.001)),
                    slippage=float(params.get("slippage", 0.001)),
                    stamp_tax=float(params.get("stamp_tax", 0.0005)),
                    normalize=str(params.get("normalize", "long_only")),
                    tradable_mask=tradable_mask,
                    up_limit=up_limit,
                    down_limit=down_limit,
                    high=high,
                    low=low,
                    take_profit=float(params.get("take_profit", 0.0)),
                    stop_loss=float(params.get("stop_loss", 0.0)),
                    trailing_stop=float(params.get("trailing_stop", 0.0)),
                )
                tear = self.performance_tear_sheet(result["strategy_returns"])
                rows.append(
                    {
                        "params": {k: v for k, v in params.items() if k in keys},
                        "total_return": tear["total_return"],
                        "annual_return": tear["annual_return"],
                        "sharpe_ratio": tear["sharpe_ratio"],
                        "max_drawdown": tear["max_drawdown"],
                        "volatility": tear["volatility"],
                        "cost": float(result["cost_summary"]["total_cost"]),
                        "trade_days": tear["trading_days"],
                    }
                )
            except Exception as e:
                rows.append({"params": dict(zip(keys, combo)), "error": str(e)[:200]})
        return {"keys": keys, "rows": rows, "n_combos": len(combos)}

    # ── 绩效报告 ─────────────────────────────────────────────

    def performance_tear_sheet(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series | None = None,
        risk_free_rate: float = 0.03,
    ) -> dict:
        """完整绩效指标"""
        returns = returns.dropna()
        n_days = len(returns)
        if n_days == 0:
            return {"error": "no data"}

        ann_factor = 252 / n_days

        # 基本统计
        total_return = float((1 + returns).prod() - 1)
        annual_return = float((1 + total_return) ** ann_factor - 1)
        volatility = float(returns.std() * np.sqrt(252))

        # Sharpe
        daily_rf = (1 + risk_free_rate) ** (1 / 252) - 1
        excess = returns - daily_rf
        sharpe = (
            float(excess.mean() / excess.std() * np.sqrt(252))
            if excess.std() > 0
            else 0.0
        )

        # Sortino
        downside = excess[excess < 0]
        downside_std = (
            float(downside.std() * np.sqrt(252)) if len(downside) > 0 else 1e-9
        )
        sortino = (
            float((annual_return - risk_free_rate) / downside_std)
            if downside_std > 0
            else 0.0
        )

        # 回撤 & Calmar
        dd_info = self.drawdown_analysis(returns)
        max_dd = dd_info["max_drawdown"]
        calmar = float(annual_return / abs(max_dd)) if max_dd != 0 else 0.0

        # VaR / CVaR (95%)
        var_95 = float(np.percentile(returns, 5))
        cvar_95 = (
            float(returns[returns <= var_95].mean())
            if (returns <= var_95).any()
            else var_95
        )

        # 胜率 & 盈亏比
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        win_rate = float(len(wins) / n_days)
        avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
        avg_loss = float(abs(losses.mean())) if len(losses) > 0 else 1e-9
        profit_loss_ratio = float(avg_win / avg_loss) if avg_loss > 0 else 0.0

        # 月度收益
        monthly = self.monthly_returns(returns)

        result = {
            "total_return": total_return,
            "annual_return": annual_return,
            "volatility": volatility,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown": max_dd,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "win_rate": win_rate,
            "profit_loss_ratio": profit_loss_ratio,
            "trading_days": n_days,
            "monthly_returns": monthly,
        }

        # 相对基准指标
        if benchmark_returns is not None:
            bm = benchmark_returns.reindex(returns.index).dropna()
            if len(bm) > 0:
                bm_total = float((1 + bm).prod() - 1)
                bm_annual = float((1 + bm_total) ** (252 / len(bm)) - 1)
                active = returns - bm
                tracking_error = float(active.std() * np.sqrt(252))
                info_ratio = (
                    float(active.mean() / active.std() * np.sqrt(252))
                    if active.std() > 0
                    else 0.0
                )
                result["benchmark"] = {
                    "total_return": bm_total,
                    "annual_return": bm_annual,
                    "tracking_error": tracking_error,
                    "information_ratio": info_ratio,
                }

        return result

    # ── 月度收益 ─────────────────────────────────────────────

    def monthly_returns(self, returns: pd.Series) -> dict:
        """按年月组织月度收益"""
        if returns.empty:
            return {}
        grouped = returns.groupby([returns.index.year, returns.index.month])
        monthly: dict = {}
        for (year, month), group in grouped:
            ret = float((1 + group).prod() - 1)
            monthly.setdefault(str(year), {})[str(month).zfill(2)] = ret
        return monthly

    # ── 回撤分析 ─────────────────────────────────────────────

    def drawdown_analysis(self, returns: pd.Series) -> dict:
        """回撤序列 + 前 5 大回撤"""
        cum = (1 + returns).cumprod()
        running_max = cum.cummax()
        drawdown = cum / running_max - 1

        max_dd = float(drawdown.min())

        # 提取前 5 大回撤区间
        top_drawdowns = []
        dd_sorted = drawdown.sort_values()
        seen_dates: set = set()
        for date, dd_val in dd_sorted.items():
            if len(top_drawdowns) >= 5:
                break
            # 跳过已收录回撤附近（±10 天）的点
            if any(abs((date - d).days) < 10 for d in seen_dates):
                continue
            seen_dates.add(date)
            # 找回撤起点（前高）
            prior = cum.loc[:date]
            peak_date = prior.idxmax()
            # 找恢复点
            after = cum.loc[date:]
            recovery_candidates = after[after >= cum.loc[peak_date]]
            recovery_date = (
                recovery_candidates.index[0] if len(recovery_candidates) > 0 else None
            )
            top_drawdowns.append(
                {
                    "trough_date": str(date.date())
                    if hasattr(date, "date")
                    else str(date),
                    "drawdown": float(dd_val),
                    "peak_date": str(peak_date.date())
                    if hasattr(peak_date, "date")
                    else str(peak_date),
                    "recovery_date": str(recovery_date.date())
                    if recovery_date is not None and hasattr(recovery_date, "date")
                    else (str(recovery_date) if recovery_date is not None else None),
                }
            )

        return {
            "drawdown_series": drawdown,
            "max_drawdown": max_dd,
            "top_drawdowns": top_drawdowns,
        }

    # ── 蒙特卡洛模拟 ────────────────────────────────────────

    def monte_carlo_simulation(
        self,
        returns: pd.Series,
        n_sims: int = 1000,
        n_days: int = 252,
        method: str = "block",
        block_size: int = 20,
    ) -> dict:
        """蒙特卡洛模拟（可选块自助 / 正态抽样）

        method:
          - block: 块自助（默认）——从历史收益序列按固定长度块有放回抽样，
            保留自相关与波动聚集（金融序列的正态假设通常不成立，块自助更贴近尾部）；
          - gaussian: 正态 iid 抽样（快速参考）。
        """
        returns = returns.dropna()
        if returns.empty:
            return {"error": "no data"}
        rng = np.random.default_rng(42)
        vals = returns.to_numpy(dtype=float)
        n_hist = len(vals)

        if method == "block":
            # 固定块自助：随机起点 + 块长截断，拼接至 n_days
            n_blocks = int(np.ceil(n_days / block_size))
            sim_returns = np.empty((n_sims, n_days))
            for s in range(n_sims):
                blocks = []
                for _ in range(n_blocks):
                    start = rng.integers(0, n_hist - block_size + 1)
                    blocks.append(vals[start : start + block_size])
                seq = np.concatenate(blocks)[:n_days]
                sim_returns[s] = seq
        else:
            mu = float(returns.mean())
            sigma = float(returns.std())
            sim_returns = rng.normal(mu, sigma, size=(n_sims, n_days))

        # 累计净值
        cum = np.cumprod(1 + sim_returns, axis=1)
        terminal = cum[:, -1]

        # 各分位数
        percentiles = {
            "p5": float(np.percentile(terminal, 5)),
            "p25": float(np.percentile(terminal, 25)),
            "p50": float(np.percentile(terminal, 50)),
            "p75": float(np.percentile(terminal, 75)),
            "p95": float(np.percentile(terminal, 95)),
        }

        # 最大回撤分布
        running_max = np.maximum.accumulate(cum, axis=1)
        dd = cum / running_max - 1
        max_dds = dd.min(axis=1)
        max_dd_stats = {
            "mean": float(max_dds.mean()),
            "p5": float(np.percentile(max_dds, 5)),
            "worst": float(max_dds.min()),
        }

        # 路径示例（取前 20 条）
        sample_paths = cum[:20].tolist()

        return {
            "n_sims": n_sims,
            "n_days": n_days,
            "method": method,
            "block_size": block_size if method == "block" else None,
            "terminal_percentiles": percentiles,
            "max_drawdown_stats": max_dd_stats,
            "sample_paths": sample_paths,
            "mean_terminal": float(terminal.mean()),
            "median_terminal": float(np.median(terminal)),
        }


# 全局单例
backtest_analysis = BacktestAnalysisService()
