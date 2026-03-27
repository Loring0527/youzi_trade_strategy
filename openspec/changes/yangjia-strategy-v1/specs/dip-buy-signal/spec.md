## ADDED Requirements

### Requirement: 低吸信号前提条件
系统 SHALL 只在赚钱效应已确认的前提下生成低吸信号。

#### Scenario: 无赚钱效应不产生信号
- **WHEN** 第一层判断为亏钱效应或恐慌效应等待模式
- **THEN** 不生成任何低吸信号

### Requirement: 低吸标的筛选条件
系统 SHALL 要求标的同时满足以下条件才触发低吸信号：属于热点概念、昨日涨停、今日低开、回调幅度合理、今日缩量。

#### Scenario: 低吸信号触发
- **WHEN** 股票属于当日热点概念（涨停数 >= 3）AND 昨日封板涨停（close[T-1] >= high_limit[T-1] × 0.999）AND 今日低开（open[T] < close[T-1] × 0.97）AND 回调未过深（open[T] > close[T-1] × 0.85）AND 今日缩量（volume[T] < volume[T-1] × 0.5）
- **THEN** 生成低吸买入信号

#### Scenario: 回调过深不买
- **WHEN** 今日开盘跌幅超过15%（open[T] <= close[T-1] × 0.85）
- **THEN** 不生成低吸信号（趋势反转，非洗盘）

#### Scenario: 放量下跌不买
- **WHEN** 今日成交量 >= 昨日成交量 × 0.8
- **THEN** 不生成低吸信号（出货特征）

### Requirement: 买入执行价格
系统 SHALL 以次日开盘价作为买入成交价（聚宽日线回测约束）。

#### Scenario: 聚宽回测买入
- **WHEN** T 日收盘生成低吸信号
- **THEN** T+1 日开盘价成交
