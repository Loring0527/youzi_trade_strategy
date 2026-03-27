## MODIFIED Requirements

### Requirement: strategy/ 目录包含四个职责模块
项目根目录 SHALL 存在 `strategy/` 目录，其中包含四个模块文件：`market_state.py`（市场状态判断）、`sector.py`（板块与龙头识别）、`signals.py`（低吸信号生成）、`position.py`（仓位与卖点管理）。

#### Scenario: 目录结构正确
- **WHEN** 执行 `ls strategy/`
- **THEN** 输出包含 `market_state.py`、`sector.py`、`signals.py`、`position.py` 四个文件（原 emotion.py 和 regime.py 合并为 market_state.py，新增 sector.py）
