## Why

`jqbacktest/main.py` 已膨胀至 1060 行，所有策略逻辑（情绪评分、大盘趋势、选股信号、仓位管理、止盈止损）混在一个文件中，每次修改一个模块都需要在大文件中定位，回测参数也散落在代码各处，维护和调参成本高。同时 `jqbacktest/modules/` 下的旧模块文件已废弃但仍占据项目空间，造成混乱。

## What Changes

- **清理废弃文件**：删除 `jqbacktest/modules/` 目录下已废弃的所有文件
- **拆分本地开发模块**：将 main.py 按职责拆分为本地可读的独立模块（情绪评分、趋势判断、选股信号、仓位/止损、策略主逻辑）
- **集中参数配置**：所有可调参数统一到 `config/params.py`，代码模块只引用配置
- **保留聚宽部署文件**：`jqbacktest/main.py` 仍作为自包含的一键粘贴部署文件，但由构建脚本或手动合并生成，不再手工维护
- **更新项目文档**：README 说明新的开发工作流（本地开发 → 合并 → 部署）

## Capabilities

### New Capabilities

- `modular-source-layout`: 将策略代码按职责拆分为本地模块，包含情绪评分、趋势判断、选股信号、仓位管理四个子模块，以及统一的参数配置入口

### Modified Capabilities

<!-- 无现有 spec，不需要 delta -->

## Impact

- `jqbacktest/modules/`：整个目录删除（废弃代码）
- `config/params.py`：扩充，接收从 main.py 中提取的所有硬编码参数
- `jqbacktest/main.py`：保留作为部署目标，内容结构不变（保持聚宽兼容）
- 本地新增 `src/` 或 `strategy/` 目录用于存放拆分后的模块源文件
- 无外部 API 或依赖变化
