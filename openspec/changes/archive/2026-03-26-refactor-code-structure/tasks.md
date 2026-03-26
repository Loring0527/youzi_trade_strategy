## 1. 清理废弃文件

- [x] 1.1 确认 `jqbacktest/modules/` 下所有文件均未被 main.py 引用（grep 验证）
- [x] 1.2 删除 `jqbacktest/modules/` 整个目录

## 2. 扩充参数配置

- [x] 2.1 将 main.py 中的 `EMOTION_PARAMS` 字典提取到 `config/params.py`
- [x] 2.2 将 main.py 中的 `PHASE_PARAMS`（各阶段止损、仓位上限等）提取到 `config/params.py`
- [x] 2.3 将 main.py 中的 `REGIME_PARAMS`（MA 窗口、仓位乘数等）提取到 `config/params.py`

## 3. 创建 strategy/ 本地模块

- [x] 3.1 新建 `strategy/` 目录，添加 `__init__.py`
- [x] 3.2 创建 `strategy/emotion.py`：提取情绪评分相关函数（涨停次日效应、涨跌停比、成交额趋势、连板高度计算）
- [x] 3.3 创建 `strategy/regime.py`：提取大盘趋势判断函数（MA60 计算、牛/震荡/熊三态判断）
- [x] 3.4 创建 `strategy/signals.py`：提取选股信号函数（低吸候选筛选、追涨候选筛选）
- [x] 3.5 创建 `strategy/position.py`：提取仓位管理函数（止盈止损检查、仓位上限计算、过热减仓）
- [x] 3.6 验证各模块在本地 Python 环境可独立 import（无 jqdata 依赖的纯逻辑函数）

## 4. 更新 jqbacktest/main.py 注释结构

- [x] 4.1 在 main.py 中按四模块添加分区注释（`# === 情绪评分 ===`、`# === 趋势判断 ===` 等），与 `strategy/` 模块对应

## 5. 更新文档

- [x] 5.1 更新 `README.md`，添加"项目结构"和"开发工作流"章节，说明 `strategy/`（本地开发）与 `jqbacktest/main.py`（聚宽部署）的双轨关系
