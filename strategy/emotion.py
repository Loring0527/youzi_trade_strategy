# -*- coding: utf-8 -*-
"""
情绪评分模块（对标炒股养家原文）

核心观察点：
  1. 涨停打板次日赚钱效应 —— 最核心（打板者次日是否还能赚钱）
  2. 涨停/跌停家数比      —— 市场多空力量对比
  3. 大盘成交额趋势       —— 量能判断市场活跃度
  4. 最高连板高度         —— 辅助：游资活跃程度

注意：
  此模块依赖 jqdata API（get_price 等），仅供参考和本地阅读。
  聚宽部署版本的同等逻辑内联在 jqbacktest/main.py 中。
"""

import numpy as np
from config.params import EMOTION

# ── 常量（镜像 main.py）─────────────────────────────────────────

PHASE_WEAK_EARLY = "WEAK_EARLY"
PHASE_WEAK_MID   = "WEAK_MID"
PHASE_WEAK_LATE  = "WEAK_LATE"
PHASE_STRONG     = "STRONG"
PHASE_HOT        = "HOT"


def _normalize(value, low, high):
    """线性归一化到 [0, 1]"""
    if high == low:
        return 0.5
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def calc_emotion_score(date, prev2_date, lu_list, lu_cnt, ld_cnt,
                       limit_up_next_day_effect_fn,
                       market_volume_trend_fn,
                       max_consecutive_boards_fn):
    """
    计算综合情绪评分（0-100）

    参数：
      date, prev2_date: 日期
      lu_list: 涨停股列表
      lu_cnt, ld_cnt: 涨停/跌停数量
      *_fn: 注入的 jqdata 相关计算函数（解耦聚宽 API）

    返回：float，0-100 的评分
    """
    ep = EMOTION

    # 指标1：涨停打板次日赚钱效应
    next_day_effect = limit_up_next_day_effect_fn(prev2_date, date)
    s_effect = _normalize(next_day_effect, -0.05, 0.05)

    # 指标2：涨停/跌停家数比
    total   = lu_cnt + ld_cnt
    ratio   = lu_cnt / total if total > 0 else 0.5
    s_ratio = _normalize(ratio, 0.3, 0.7)

    # 指标3：大盘成交额趋势
    vol_trend = market_volume_trend_fn(date)
    s_vol     = _normalize(vol_trend, -0.2, 0.2)

    # 指标4：最高连板高度（辅助）
    max_boards = max_consecutive_boards_fn(date, lu_list)
    s_boards   = _normalize(max_boards, 0, 8)

    score = (
        s_effect * ep["weight_next_day_effect"] +
        s_ratio  * ep["weight_limit_ratio"]     +
        s_vol    * ep["weight_volume_trend"]     +
        s_boards * ep["weight_max_boards"]
    ) * 100

    return round(float(np.clip(score, 0, 100)), 2)


def classify_phase(score, score_history):
    """
    五阶段分类

    阈值固定（不随制度变化）：
      HOT ≥ 70    → 过热高潮
      STRONG ≥ 50 → 赚钱效应
      < 50        → 弱势三阶段（按趋势方向区分初/中/末期）

    返回：阶段常量字符串
    """
    ep        = EMOTION
    hot_th    = ep["hot_threshold"]
    strong_th = ep["strong_threshold"]

    if score >= hot_th:
        return PHASE_HOT
    if score >= strong_th:
        return PHASE_STRONG

    # 弱势区间：用趋势方向区分三阶段
    window = ep["trend_window"]
    if len(score_history) >= window:
        recent_avg = float(np.mean(score_history[-window:]))
        trend      = score - recent_avg
    else:
        trend = 0.0

    if trend >= ep["trend_rising"]:
        return PHASE_WEAK_LATE   # 情绪回升 → 弱势末期
    elif trend <= ep["trend_falling"]:
        return PHASE_WEAK_EARLY  # 情绪恶化 → 弱势初期
    else:
        return PHASE_WEAK_MID    # 情绪平稳 → 弱势中期
