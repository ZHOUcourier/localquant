系统内置技能skills

------

## 一、系统内置技能（builtin）— 共 30 个

json



```json
[
  {
    "name": "remember",
    "display_name": "记录长期记忆",
    "description": "把用户的一条长期、稳定偏好或事实保存为跨会话记忆。适合记录投资风格、可接受回撤、长期市场范围、资金规模、经验水平和习惯。不要记录本次回测区间、临时代码参数、当前对话中间步骤或其它一次性请求；已有相同文本不要重复保存。",
    "category": "记忆",
    "category_id": "memory",
    "params": ["content", "kind"]
  },
  {
    "name": "generate_stock_strategy_code",
    "display_name": "生成股票策略代码",
    "description": "生成或修改完整的 A 股 panda_quantflow 策略代码并写入画板。只能生成股票策略，市场由 Tool 名固定为 stock。",
    "category": "策略",
    "category_id": "strategy",
    "params": ["code", "name", "summary", "stock"]
  },
  {
    "name": "generate_future_strategy_code",
    "display_name": "生成期货策略代码",
    "description": "生成或修改完整的国内期货 panda_quantflow 策略代码并写入画板。只能生成期货策略，市场由 Tool 名固定为 future。",
    "category": "策略",
    "category_id": "strategy",
    "params": ["code", "name", "summary", "stock", "requested_order_callbacks"]
  },
  {
    "name": "generate_hk_strategy_code",
    "display_name": "生成港股策略代码",
    "description": "生成或修改完整的港股 panda_quantflow 策略代码并写入画板。只能生成港股策略，市场由 Tool 名固定为 hk。",
    "category": "策略",
    "category_id": "strategy",
    "params": ["code", "name", "summary", "stock"]
  },
  {
    "name": "generate_us_strategy_code",
    "display_name": "生成美股策略代码",
    "description": "生成或修改完整的美股 panda_quantflow 策略代码并写入画板。只能生成美股策略，市场由 Tool 名固定为 us。",
    "category": "策略",
    "category_id": "strategy",
    "params": ["code", "name", "summary", "stock"]
  },
  {
    "name": "list_strategy_versions",
    "display_name": "查看策略版本列表",
    "description": "列出当前策略的历史版本（v1, v2…）：版本号、改动说明、标签、是否标星、来源、时间。",
    "category": "策略",
    "category_id": "strategy",
    "params": ["strategy_id"]
  },
  {
    "name": "get_strategy_version",
    "display_name": "读取策略版本",
    "description": "读取某个历史版本的源码与说明（只读，不改画板）。",
    "category": "策略",
    "category_id": "strategy",
    "params": ["strategy_id", "version_number"]
  },
  {
    "name": "revert_strategy_to_version",
    "display_name": "回滚策略版本",
    "description": "把策略回滚到某个历史版本：将该版代码复制成新版本并写回画板，历史不会丢。",
    "category": "策略",
    "category_id": "strategy",
    "params": ["strategy_id", "version_number"]
  },
  {
    "name": "list_strategies",
    "display_name": "查看策略列表",
    "description": "列出当前用户所有策略，以及每条策略最近一次成功回测的总收益、夏普与迷你曲线。",
    "category": "策略",
    "category_id": "strategy",
    "params": []
  },
  {
    "name": "set_backtest_params",
    "display_name": "设置回测参数",
    "description": "调整右侧画板的回测参数（起止日期、初始资金、成本、基准、频率等），不立刻开跑。",
    "category": "回测",
    "category_id": "backtest",
    "params": ["period_start", "period_end", "init_balance", "commission_rate", "slippage", "standard_symbol", "margin_rate", "frequency"]
  },
  {
    "name": "run_backtest",
    "display_name": "运行策略回测",
    "description": "对当前策略提交真实云端回测任务，并在对话中展示进度与结果卡片。",
    "category": "回测",
    "category_id": "backtest",
    "params": ["strategy_id"]
  },
  {
    "name": "get_backtest_result",
    "display_name": "读取回测结果",
    "description": "只读获取一次真实回测结果，用于诊断无成交、失败原因或异常指标。",
    "category": "回测",
    "category_id": "backtest",
    "params": ["backtest_run_id", "strategy_id"]
  },
  {
    "name": "create_optimization_task",
    "display_name": "创建调优任务",
    "description": "为策略创建参数调优任务，在多组参数下回测并挑选表现最好的组合。",
    "category": "调优",
    "category_id": "optimization",
    "params": ["strategy_id", "name", "description", "objective", "search_space", "period_start", "period_end"]
  },
  {
    "name": "list_optimization_tasks",
    "display_name": "查看调优任务列表",
    "description": "列出当前用户所有调优任务（进度、最优参数、最优指标）。",
    "category": "调优",
    "category_id": "optimization",
    "params": ["strategy_id"]
  },
  {
    "name": "start_optimization_task",
    "display_name": "启动调优任务",
    "description": "启动或重跑一个调优任务。",
    "category": "调优",
    "category_id": "optimization",
    "params": ["task_id"]
  },
  {
    "name": "cancel_optimization_task",
    "display_name": "取消调优任务",
    "description": "取消一个正在跑或排队的调优任务。",
    "category": "调优",
    "category_id": "optimization",
    "params": ["task_id"]
  },
  {
    "name": "create_live_account",
    "display_name": "创建仿真盘",
    "description": "派发「确认建盘」卡片；用户确认后才真正创建仿真盘账户。",
    "category": "仿真交易",
    "category_id": "live",
    "params": ["name", "init_balance", "mode", "strategy_id"]
  },
  {
    "name": "start_live",
    "display_name": "启动仿真盘",
    "description": "派发「确认启动」卡片；用户确认后才真正启动仿真盘。",
    "category": "仿真交易",
    "category_id": "live",
    "params": ["live_account_id"]
  },
  {
    "name": "stop_live",
    "display_name": "停止仿真盘",
    "description": "派发「确认停止」卡片；用户确认后才真正停止仿真盘。",
    "category": "仿真交易",
    "category_id": "live",
    "params": ["live_account_id"]
  },
  {
    "name": "list_live_accounts",
    "display_name": "查看仿真盘列表",
    "description": "列出当前用户所有仿真盘，含余额、PnL 与收益曲线。",
    "category": "仿真交易",
    "category_id": "live",
    "params": []
  },
  {
    "name": "confirm_pending_order",
    "display_name": "确认待处理订单",
    "description": "确认一笔 pending_confirm 状态的订单。",
    "category": "仿真交易",
    "category_id": "live",
    "params": ["order_id"]
  },
  {
    "name": "cancel_pending_order",
    "display_name": "取消待处理订单",
    "description": "撤销一笔 pending_confirm 订单。",
    "category": "仿真交易",
    "category_id": "live",
    "params": ["order_id"]
  },
  {
    "name": "bind_chat_target",
    "display_name": "绑定对话目标",
    "description": "切换当前对话绑定的策略槽或仿真盘槽。",
    "category": "对话",
    "category_id": "chat",
    "params": ["kind", "id"]
  },
  {
    "name": "query_market_data",
    "display_name": "查询行情数据",
    "description": "用 panda_data 查询 A 股/国内期货的行情或基本面表格（只读），在对话中展示表格卡片。",
    "category": "对话",
    "category_id": "chat",
    "params": ["dataset", "symbols", "start_date", "end_date", "fields", "exchange", "indicator", "side", "top_n", "universe", "level", "concept", "start_quarter", "end_quarter"]
  },
  {
    "name": "generate_stock_factor_code",
    "display_name": "生成股票因子代码",
    "description": "生成或修改 A 股因子。市场由 Tool 名固定为 stock。",
    "category": "因子",
    "category_id": "factor",
    "params": ["code", "name", "description", "code_type", "factor_id"]
  },
  {
    "name": "generate_future_factor_code",
    "display_name": "生成期货因子代码",
    "description": "生成或修改国内期货因子。市场由 Tool 名固定为 future。",
    "category": "因子",
    "category_id": "factor",
    "params": ["code", "name", "description", "code_type", "factor_id"]
  },
  {
    "name": "generate_hk_factor_code",
    "display_name": "生成港股因子代码",
    "description": "生成或修改港股因子。市场由 Tool 名固定为 hk。",
    "category": "因子",
    "category_id": "factor",
    "params": ["code", "name", "description", "code_type", "factor_id"]
  },
  {
    "name": "generate_us_factor_code",
    "display_name": "生成美股因子代码",
    "description": "生成或修改美股因子。市场由 Tool 名固定为 us。",
    "category": "因子",
    "category_id": "factor",
    "params": ["code", "name", "description", "code_type", "factor_id"]
  },
  {
    "name": "run_factor_analysis",
    "display_name": "运行因子分析",
    "description": "对因子做 IC 分析与分组回测，返回 IC、分组收益、多空组合等指标与图表。",
    "category": "因子",
    "category_id": "factor",
    "params": ["factor_id", "period_start", "period_end", "adjustment_cycle", "group_number", "factor_direction", "stock_pool", "market_type"]
  },
  {
    "name": "list_factors",
    "display_name": "查看因子列表",
    "description": "列出用户所有因子，附带最近一次分析的 IC_mean / IC_IR / 分组单调性。",
    "category": "因子",
    "category_id": "factor",
    "params": []
  }
]
```

------

## 二、用户自定义技能（user skills）

json



```json
[]
```

（空数组，该用户没有自定义技能。）

------

## 汇总

| #    | name                          | display_name     | category (category_id) | params                                                       |
| :--- | :---------------------------- | :--------------- | :--------------------- | :----------------------------------------------------------- |
| 1    | remember                      | 记录长期记忆     | 记忆 (memory)          | content, kind                                                |
| 2    | generate_stock_strategy_code  | 生成股票策略代码 | 策略 (strategy)        | code, name, summary, stock                                   |
| 3    | generate_future_strategy_code | 生成期货策略代码 | 策略 (strategy)        | code, name, summary, stock, requested_order_callbacks        |
| 4    | generate_hk_strategy_code     | 生成港股策略代码 | 策略 (strategy)        | code, name, summary, stock                                   |
| 5    | generate_us_strategy_code     | 生成美股策略代码 | 策略 (strategy)        | code, name, summary, stock                                   |
| 6    | list_strategy_versions        | 查看策略版本列表 | 策略 (strategy)        | strategy_id                                                  |
| 7    | get_strategy_version          | 读取策略版本     | 策略 (strategy)        | strategy_id, version_number                                  |
| 8    | revert_strategy_to_version    | 回滚策略版本     | 策略 (strategy)        | strategy_id, version_number                                  |
| 9    | list_strategies               | 查看策略列表     | 策略 (strategy)        | *(无)*                                                       |
| 10   | set_backtest_params           | 设置回测参数     | 回测 (backtest)        | period_start, period_end, init_balance, commission_rate, slippage, standard_symbol, margin_rate, frequency |
| 11   | run_backtest                  | 运行策略回测     | 回测 (backtest)        | strategy_id                                                  |
| 12   | get_backtest_result           | 读取回测结果     | 回测 (backtest)        | backtest_run_id, strategy_id                                 |
| 13   | create_optimization_task      | 创建调优任务     | 调优 (optimization)    | strategy_id, name, description, objective, search_space, period_start, period_end |
| 14   | list_optimization_tasks       | 查看调优任务列表 | 调优 (optimization)    | strategy_id                                                  |
| 15   | start_optimization_task       | 启动调优任务     | 调优 (optimization)    | task_id                                                      |
| 16   | cancel_optimization_task      | 取消调优任务     | 调优 (optimization)    | task_id                                                      |
| 17   | create_live_account           | 创建仿真盘       | 仿真交易 (live)        | name, init_balance, mode, strategy_id                        |
| 18   | start_live                    | 启动仿真盘       | 仿真交易 (live)        | live_account_id                                              |
| 19   | stop_live                     | 停止仿真盘       | 仿真交易 (live)        | live_account_id                                              |
| 20   | list_live_accounts            | 查看仿真盘列表   | 仿真交易 (live)        | *(无)*                                                       |
| 21   | confirm_pending_order         | 确认待处理订单   | 仿真交易 (live)        | order_id                                                     |
| 22   | cancel_pending_order          | 取消待处理订单   | 仿真交易 (live)        | order_id                                                     |
| 23   | bind_chat_target              | 绑定对话目标     | 对话 (chat)            | kind, id                                                     |
| 24   | query_market_data             | 查询行情数据     | 对话 (chat)            | dataset, symbols, start_date, end_date, fields, exchange, indicator, side, top_n, universe, level, concept, start_quarter, end_quarter |
| 25   | generate_stock_factor_code    | 生成股票因子代码 | 因子 (factor)          | code, name, description, code_type, factor_id                |
| 26   | generate_future_factor_code   | 生成期货因子代码 | 因子 (factor)          | code, name, description, code_type, factor_id                |
| 27   | generate_hk_factor_code       | 生成港股因子代码 | 因子 (factor)          | code, name, description, code_type, factor_id                |
| 28   | generate_us_factor_code       | 生成美股因子代码 | 因子 (factor)          | code, name, description, code_type, factor_id                |
| 29   | run_factor_analysis           | 运行因子分析     | 因子 (factor)          | factor_id, period_start, period_end, adjustment_cycle, group_number, factor_direction, stock_pool, market_type |
| 30   | list_factors                  | 查看因子列表     | 因子 (factor)          | *(无)*                                                       |

------

**任务完成**：通过 `evaluate_script` 直接调用页面内 `fetch` 成功获取了 `/pandaApi/agent_quant/api/skills/builtin`（30 个内置技能）和 `/pandaApi/agent_quant/api/skills/user`（空数组）的完整 JSON 数据，无截断、无遗漏。每个技能包含的全部字段为：`name`、`display_name`、`description`、`category`、`category_id`、`params`。