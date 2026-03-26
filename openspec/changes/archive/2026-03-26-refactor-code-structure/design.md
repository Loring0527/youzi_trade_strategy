## Context

当前 `jqbacktest/main.py`（1060行）承担了所有职责：常量定义、参数配置、情绪评分、趋势判断、选股信号、仓位管理、止盈止损、聚宽生命周期钩子（initialize/before_trading_start/handle_data/after_trading_end）。这使得单次参数调优需要在大文件中反复定位，版本间 diff 难以阅读。

此外 `jqbacktest/modules/` 下存有 v1.x 时代的废弃文件（`market_emotion.py`、`position.py`、`signals.py`、`stock_filter.py`），已不再被 main.py 引用，但仍存在造成混乱。

聚宽平台要求策略代码**单文件、无外部 import**（除 jqdata/pandas/numpy），因此本地模块拆分后仍需维护一个合并后的部署文件。

## Goals / Non-Goals

**Goals:**
- 将策略逻辑按职责拆分为 4 个本地模块（情绪评分、趋势判断、选股信号、仓位管理）
- 所有可调参数集中到 `config/params.py`，模块只引用配置
- 删除废弃的 `jqbacktest/modules/` 目录
- 明确"本地开发文件"与"聚宽部署文件"的关系，更新 README

**Non-Goals:**
- 改变任何策略逻辑或参数数值（纯结构重构）
- 实现自动化构建/合并脚本（手动合并即可，不引入工具链）
- 修改聚宽部署文件 `jqbacktest/main.py` 的实际行为

## Decisions

### 1. 新增 `strategy/` 目录作为本地模块根

**决定**：在项目根新增 `strategy/` 目录，而非复用废弃的 `jqbacktest/modules/`。

**理由**：`modules/` 命名模糊且历史包袱重；`strategy/` 语义更清晰，与 `config/`、`jqbacktest/` 同级，结构一目了然。

**备选方案**：复用 `jqbacktest/modules/` → 否决，旧文件会造成混淆。

### 2. 四模块划分

| 模块文件 | 职责 |
|---------|------|
| `strategy/emotion.py` | 情绪评分：涨停次日效应、涨跌停比、成交额趋势、连板高度 |
| `strategy/regime.py` | 大盘趋势判断：牛/震荡/熊三态，MA60 等计算 |
| `strategy/signals.py` | 选股信号：低吸候选、追涨候选、各阶段筛选逻辑 |
| `strategy/position.py` | 仓位管理：止盈止损、仓位上限计算、减仓逻辑 |

`jqbacktest/main.py` 仍保留完整可运行版本，内部按相同四段结构注释分区，便于与本地模块对照。

**备选方案**：不拆分，仅加注释分区 → 否决，本地模块可独立单元测试，注释分区不能。

### 3. params.py 扩充策略

**决定**：`config/params.py` 接收从 main.py 提取的所有 `EMOTION_PARAMS`、`PHASE_PARAMS`、`REGIME_PARAMS` 等字典，本地模块从 `config.params` import，main.py 中参数保持内联（聚宽不支持外部 import）。

**理由**：两套代码（本地模块 vs 部署文件）共享同一份参数语义定义，调参时只需看 params.py 即可确定所有可调项。

### 4. 不引入构建脚本

**决定**：不编写自动合并脚本，开发者手动同步本地模块改动到 main.py。

**理由**：当前团队规模（1人）不值得引入构建工具链；手动同步配合 git diff 已足够。若未来频繁修改再考虑脚本化。

## Risks / Trade-offs

- **[风险] 本地模块与 main.py 逻辑漂移**：手动同步可能导致两者不一致。→ 缓解：README 明确说明同步规则，每次 commit 的 diff 应覆盖两处同样的逻辑变更。
- **[取舍] 增加文件数量**：从 1 个文件变为 5+ 个文件，初次理解成本稍高。→ 代价可接受，换取长期可维护性。
- **[风险] 删除 modules/ 不可逆**：若有遗漏引用会造成错误。→ 缓解：删除前用 grep 确认无引用。

## Migration Plan

1. 确认 `jqbacktest/modules/` 无任何引用后删除整个目录
2. 新建 `strategy/` 目录，按四模块划分创建文件，内容从 main.py 提取
3. 扩充 `config/params.py`，列明所有可调参数及默认值
4. 更新 `jqbacktest/main.py` 内部注释分区（对照本地模块）
5. 更新 README：说明 `strategy/` 为本地开发用，`jqbacktest/main.py` 为聚宽部署文件

回滚：git revert 即可，聚宽部署文件内容不变，无运行时风险。

## Open Questions

- 是否需要为 `strategy/` 下的模块补充 pytest 单元测试？（当前无测试覆盖）
