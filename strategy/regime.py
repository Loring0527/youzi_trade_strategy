# -*- coding: utf-8 -*-
"""
大盘趋势判断模块（第一层：宏观）

判断逻辑：基于沪深300相对60日均线的位置
  CSI300 > MA60 × 105% → 牛市（BULL）
  CSI300 < MA60 ×  95% → 熊市（BEAR）
  介于两者               → 震荡（NEUTRAL）

制度影响：
  牛市 × 1.2 / 震荡 × 1.0 / 熊市 × 0.6（仓位上限乘数）
  不影响情绪阶段阈值（HOT/STRONG 阈值固定）

注意：
  此模块依赖 jqdata API，仅供参考和本地阅读。
  聚宽部署版本的同等逻辑内联在 jqbacktest/main.py 中。
"""

from config.params import REGIME, REGIME_POSITION_FACTOR

REGIME_BULL    = "BULL"
REGIME_NEUTRAL = "NEUTRAL"
REGIME_BEAR    = "BEAR"

REGIME_CN = {
    REGIME_BULL:    "牛市",
    REGIME_NEUTRAL: "震荡",
    REGIME_BEAR:    "熊市",
}


def detect_market_regime(date, get_price_fn):
    """
    判断大盘趋势

    参数：
      date: 判断日期（使用该日及之前数据）
      get_price_fn: jqdata get_price 函数（注入，解耦 API）

    返回：REGIME_BULL / REGIME_NEUTRAL / REGIME_BEAR
    """
    try:
        p      = REGIME
        prices = get_price_fn(
            "000300.XSHG", end_date=date,
            count=p["ma_period"],
            fields=["close"], frequency="daily",
        )
        if prices is None or len(prices) < p["ma_period"]:
            return REGIME_NEUTRAL

        current = float(prices["close"].iloc[-1])
        ma60    = float(prices["close"].mean())

        if current > ma60 * p["bull_threshold"]:
            return REGIME_BULL
        elif current < ma60 * p["bear_threshold"]:
            return REGIME_BEAR
        else:
            return REGIME_NEUTRAL
    except Exception:
        return REGIME_NEUTRAL


def get_position_factor(regime):
    """
    获取制度仓位乘数

    参数：regime 大盘趋势常量
    返回：float，仓位上限乘数
    """
    return REGIME_POSITION_FACTOR.get(regime, 1.0)
