### Requirement: strategy/ 目录包含四个职责模块
项目根目录 SHALL 存在 `strategy/` 目录，其中包含四个模块文件：`emotion.py`（情绪评分）、`regime.py`（大盘趋势）、`signals.py`（选股信号）、`position.py`（仓位管理）。

#### Scenario: 目录结构正确
- **WHEN** 执行 `ls strategy/`
- **THEN** 输出包含 `emotion.py`、`regime.py`、`signals.py`、`position.py` 四个文件

### Requirement: 参数集中到 config/params.py
`config/params.py` SHALL 定义所有策略可调参数，包括 EMOTION_PARAMS、PHASE_PARAMS、REGIME_PARAMS 及其子参数，本地模块 SHALL 从该文件 import 参数而非硬编码。

#### Scenario: 本地模块无硬编码数值参数
- **WHEN** 检查 `strategy/` 下任意模块文件
- **THEN** 不包含孤立的浮点数阈值（如 0.40、70、50），所有参数均引用自 `config.params`

### Requirement: 废弃模块目录已删除
`jqbacktest/modules/` 目录 SHALL NOT 存在于项目中。

#### Scenario: 废弃目录不存在
- **WHEN** 执行 `ls jqbacktest/`
- **THEN** 输出不包含 `modules` 目录

### Requirement: 聚宽部署文件保持自包含
`jqbacktest/main.py` SHALL 仍为单文件自包含，可直接粘贴到聚宽策略编辑器运行，不依赖 `strategy/` 或 `config/` 中的任何模块。

#### Scenario: 部署文件无本地模块依赖
- **WHEN** 检查 `jqbacktest/main.py` 的 import 语句
- **THEN** 仅包含 `jqdata`、`pandas`、`numpy` 等聚宽平台支持的库，不包含 `strategy` 或 `config` 模块的 import

### Requirement: README 说明双轨工作流
`README.md` SHALL 包含一节说明"本地开发"与"聚宽部署"的双轨工作流：`strategy/` 用于本地开发和参数调优，`jqbacktest/main.py` 用于聚宽部署，手动同步变更。

#### Scenario: README 包含工作流说明
- **WHEN** 阅读 `README.md`
- **THEN** 能找到说明 `strategy/` 和 `jqbacktest/main.py` 用途区别的章节
