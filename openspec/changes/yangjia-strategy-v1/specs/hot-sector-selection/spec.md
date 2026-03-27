## ADDED Requirements

### Requirement: 使用聚宽概念板块
系统 SHALL 使用聚宽概念板块（非行业板块）作为热点板块的识别单元。

#### Scenario: 板块数据来源
- **WHEN** 系统需要板块分类数据
- **THEN** 使用聚宽 get_concept_stocks() 和 get_concepts() API 获取概念板块成分

### Requirement: 热点板块识别
系统 SHALL 将当日涨停数 >= 3 的概念板块判定为热点板块，进入候选池。

#### Scenario: 概念板块激活
- **WHEN** 某概念板块当日涨停股数量 >= 3
- **THEN** 该概念板块进入当日热点候选池

#### Scenario: 概念板块未激活
- **WHEN** 某概念板块当日涨停股数量 < 3
- **THEN** 该概念板块不进入候选池

### Requirement: 板块新题材判断
系统 SHALL 通过比较前2日涨停数来区分新启动题材与持续热点。

#### Scenario: 新题材激活
- **WHEN** 当日概念板块涨停数 >= 3 AND 前2日该概念涨停数均 < 3
- **THEN** 标记为"新激活板块"，优先进入龙头识别流程
