# -*- coding: utf-8 -*-
"""
仓位管理模块

负责：
  - 止盈止损信号生成
  - 持仓记录维护（最高价、持仓天数）
  - 阶段止损比例查询

止盈止损规则（对标养家原文）：
  1. 止损：弱势初期 -5%，其余阶段 -7%
  2. 浮盈保护：盈利 > 15% 后，从峰值回撤 > 7% 全清
  3. 过热减仓：HOT 阶段 + 浮盈 > 5%，减仓一半
  4. 超时清仓：持仓 > 10 天且盈亏 < 2% 清仓

注意：
  此模块的 generate_sell_signals / update_position_records 依赖
  聚宽 context.portfolio 对象，仅供参考和本地阅读。
  聚宽部署版本的同等逻辑内联在 jqbacktest/main.py 中。
"""

from config.params import EXIT, WEAK_EARLY, WEAK_MID, WEAK_LATE_DIP, STRONG

PHASE_WEAK_EARLY = "WEAK_EARLY"
PHASE_WEAK_MID   = "WEAK_MID"
PHASE_WEAK_LATE  = "WEAK_LATE"
PHASE_STRONG     = "STRONG"
PHASE_HOT        = "HOT"

PHASE_CN = {
    PHASE_WEAK_EARLY: "弱势初期",
    PHASE_WEAK_MID:   "弱势中期",
    PHASE_WEAK_LATE:  "弱势末期",
    PHASE_STRONG:     "赚钱效应",
    PHASE_HOT:        "过热高潮",
}


def get_stop_loss(phase):
    """
    获取当前阶段的止损比例

    弱势初期更严格（-5%），其余阶段 -7%
    """
    return {
        PHASE_WEAK_EARLY: WEAK_EARLY["stop_loss"],
        PHASE_WEAK_MID:   WEAK_MID["stop_loss"],
        PHASE_WEAK_LATE:  WEAK_LATE_DIP["stop_loss"],
        PHASE_STRONG:     STRONG["stop_loss"],
        PHASE_HOT:        -0.07,
    }.get(phase, -0.07)


def generate_sell_signals(phase, positions, position_records):
    """
    生成卖出信号

    参数：
      phase: 当前情绪阶段
      positions: dict-like，{stock: pos}，pos 含 avg_cost / price / value
      position_records: dict，{stock: {max_price, hold_days, entry_date}}

    返回：list of signal dict
      {stock, ratio(1.0=全清/0.5=减半), reason, gain_pct, current_price}
    """
    signals   = []
    ep        = EXIT
    stop_loss = get_stop_loss(phase)

    for stock, pos in positions.items():
        try:
            entry   = pos.avg_cost
            current = pos.price
            rec     = position_records.get(stock, {})
            max_p   = rec.get("max_price", current)
            days    = rec.get("hold_days", 0)

            if entry <= 0:
                continue

            gain = (current - entry) / entry
            dd   = (current - max_p) / max_p if max_p > 0 else 0

            exit_flag  = False
            exit_ratio = 1.0
            reason     = ""

            # 止损（弱势初期更严格）
            if gain <= stop_loss:
                exit_flag = True
                reason    = (
                    f"止损（{gain*100:.1f}%，"
                    f"{PHASE_CN.get(phase, phase)}阶段）"
                )

            # 浮盈保护：盈利>15%后从峰值回撤>7%止盈
            elif (gain >= ep["profit_protect_trigger"]
                  and dd <= -ep["profit_protect_drawdown"]):
                exit_flag = True
                reason    = (
                    f"浮盈保护（峰值浮盈"
                    f"{((max_p - entry) / entry) * 100:.1f}%，"
                    f"回撤{dd*100:.1f}%）"
                )

            # 过热减仓：浮盈>5%减半
            elif phase == PHASE_HOT and gain >= ep["hot_reduce_trigger"]:
                exit_flag  = True
                exit_ratio = 0.5
                reason     = f"过热减仓（浮盈{gain*100:.1f}%）"

            # 超时清仓：持仓超10天且盈亏<2%
            elif days >= ep["max_hold_days"] and gain < ep["timeout_min_gain"]:
                exit_flag = True
                reason    = f"持仓{days}天未走强（{gain*100:.1f}%）"

            if exit_flag:
                signals.append({
                    "stock":         stock,
                    "ratio":         exit_ratio,
                    "reason":        reason,
                    "gain_pct":      round(gain * 100, 2),
                    "current_price": current,
                })
        except Exception:
            continue

    return signals


def update_position_records(positions, position_records, current_date_str):
    """
    维护持仓最高价和持仓天数

    参数：
      positions: dict-like，{stock: pos}，pos 含 price
      position_records: dict（原地修改）
      current_date_str: 当日日期字符串

    返回：更新后的 position_records
    """
    for stock, pos in positions.items():
        price = pos.price
        if stock not in position_records:
            position_records[stock] = {
                "max_price":  price,
                "hold_days":  1,
                "entry_date": current_date_str,
            }
        else:
            rec = position_records[stock]
            rec["hold_days"] += 1
            if price > rec["max_price"]:
                rec["max_price"] = price

    current_stocks = set(positions.keys())
    for s in list(position_records.keys()):
        if s not in current_stocks:
            del position_records[s]

    return position_records
