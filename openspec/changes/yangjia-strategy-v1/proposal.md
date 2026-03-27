## Why

现有代码（v2.x）是由 AI 自动生成的，策略逻辑与炒股养家原文存在较多偏差（HOT阈值敏感、盈亏比倒置、大量参数缺乏原文依据）。本次从第一性原理重新设计，以养家原文为唯一依据，建立四层决策框架并实现可回测的 v3 策略。

## What Changes

- 替换第一层市场状态判断：废弃情绪评分五阶段，改用三态模型（赚钱效应/亏钱效应/恐慌效应）
- 新增赚钱效应量化判断：涨停数前置条件 + 打板次日赚钱效应 + 炸板率 + 连板存活率三指标
- 新增恐慌效应量化判断：大盘指数（沪深平均）10日累计跌幅 + 单日跌幅触发
- 新增第二层板块与个股选择：热点概念识别 + 早鸟频率龙头算法 + 低吸信号生成
- 新增第三层仓位决策：固定单笔30%，最多同时持2只
- 新增第四层卖点管理：四优先级卖出规则（市场环境变化 > 止损 > 浮盈保护 > 超时）
- 重写 `jqbacktest/main.py` 实现以上逻辑

## Capabilities

### New Capabilities

- `market-state-detection`: 三态市场状态判断（赚钱效应/亏钱效应/恐慌效应）及每日重新计算逻辑
- `hot-sector-selection`: 基于聚宽概念板块的热点板块识别（当日涨停数 >= 3）
- `dragon-head-identification`: 早鸟频率算法识别龙头股（60日滚动窗口，板块首发激活统计）
- `dip-buy-signal`: 低吸信号生成（昨日涨停 + 今日低开缩量回调）
- `position-sizing`: 仓位决策规则（单笔30%，最多2只）
- `exit-management`: 四优先级卖出管理（市场环境 > 止损-5% > 浮盈保护 > 超时清仓）

### Modified Capabilities

- `modular-source-layout`: strategy/ 各模块需对应新的四层框架（原有模块逻辑已过时）

## Impact

- `jqbacktest/main.py`：完全重写，实现新四层框架
- `strategy/emotion.py`：废弃情绪评分，改为市场状态判断
- `strategy/regime.py`：废弃大盘趋势三态，合并入市场状态判断
- `strategy/signals.py`：重写低吸信号逻辑，新增早鸟频率计算
- `strategy/position.py`：止损从-7%调整为-5%，浮盈保护峰值回撤从-7%调整为-5%
- `config/params.py`：参数随策略逻辑同步更新
