## ADDED Requirements

### Requirement: 单笔仓位上限
系统 SHALL 将每次买入的仓位固定为总资金的30%。

#### Scenario: 单笔买入仓位
- **WHEN** 触发买入信号
- **THEN** 买入金额 = 总资金 × 30%，不超过此上限

### Requirement: 最大同时持股数
系统 SHALL 限制同时持有的股票数量不超过2只。

#### Scenario: 持股已满不新买
- **WHEN** 当前持股数量 >= 2
- **THEN** 不执行新的买入信号，等待现有持仓出清

#### Scenario: 持股未满可以买入
- **WHEN** 当前持股数量 < 2 AND 存在低吸信号
- **THEN** 允许执行买入

### Requirement: 一次建仓不加仓
系统 SHALL 对同一只股票只建仓一次，不执行加仓操作。

#### Scenario: 已持有不加仓
- **WHEN** 已持有某股票 AND 该股票再次出现买入信号
- **THEN** 忽略该信号，不加仓
