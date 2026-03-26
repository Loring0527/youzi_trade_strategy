# -*- coding: utf-8 -*-
"""
选股信号模块

负责：
  - 低吸候选池筛选（弱势初/中/末期共用，参数各异）
  - 追涨候选池筛选（赚钱效应/弱势末期追涨部分）
  - 买入信号生成（五阶段操作逻辑）

筛选逻辑（对标养家原文）：
  低吸：近N天涨停 + 从高点回调X% + 量缩至均量X% + 不低于均线X%
  追涨：昨日涨幅 > 3% + 换手率 > 3%

注意：
  此模块依赖 jqdata API，仅供参考和本地阅读。
  聚宽部署版本的同等逻辑内联在 jqbacktest/main.py 中。
"""

import pandas as pd
from config.params import (
    POSITION, REGIME_POSITION_FACTOR,
    WEAK_EARLY, WEAK_MID, WEAK_LATE_DIP, WEAK_LATE_CHASE, STRONG,
)

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


def _score_dip_from_df(stock, prices, p):
    """计算低吸评分（无 API 调用，基于预取数据）"""
    if prices["paused"].iloc[-1] == 1:
        return None

    today_close = prices["close"].iloc[-1]
    today_vol   = prices["volume"].iloc[-1]

    recent_window = p["recent_limit_up_days"]
    recent        = prices.iloc[-(recent_window + 1): -1]
    if recent.empty:
        return None

    # 条件1：近N天内有涨停记录
    if not (recent["close"] >= recent["high_limit"] * 0.999).any():
        return None

    # 条件2：从近期高点回调 >= 阶段设定值
    recent_high = recent["high"].max()
    if recent_high <= 0:
        return None
    pullback = (recent_high - today_close) / recent_high
    if pullback < p["pullback_from_high_min"]:
        return None

    # 条件3：量缩
    shrink_days = p["volume_shrink_days"]
    avg_vol     = prices["volume"].iloc[-(shrink_days + 1): -1].mean()
    if avg_vol <= 0 or today_vol >= avg_vol * p["volume_shrink_ratio"]:
        return None

    # 条件4：不低于均线阶段设定比例
    ma_period = p["trend_ma_period"]
    if len(prices) < ma_period:
        return None
    ma60 = prices["close"].tail(ma_period).mean()
    if today_close < ma60 * p["price_above_ma_ratio"]:
        return None

    pullback_score = min(pullback / 0.30, 1.0) * 40
    vol_score      = min(
        (1 - today_vol / avg_vol) / (1 - p["volume_shrink_ratio"]), 1.0
    ) * 30
    ma_score       = min(today_close / ma60 / 1.2, 1.0) * 30
    dip_score      = pullback_score + vol_score + ma_score

    return {
        "stock":             stock,
        "close":             today_close,
        "pullback_pct":      round(pullback * 100, 2),
        "volume_shrink_pct": round((1 - today_vol / avg_vol) * 100, 2),
        "ma60":              round(ma60, 2),
        "dip_score":         round(dip_score, 2),
    }


def filter_dip_candidates(universe, prev_date, params,
                          get_fundamentals_fn, get_price_fn, query_fn, valuation):
    """
    低吸候选池筛选

    参数：
      universe: 全市场股票池
      prev_date: 昨日日期
      params: 阶段参数字典（WEAK_EARLY / WEAK_MID / WEAK_LATE_DIP）
      *_fn / valuation: 注入的 jqdata 对象
    """
    try:
        q = query_fn(valuation.code).filter(
            valuation.circulating_market_cap >= params["market_cap_min_yi"],
            valuation.circulating_market_cap <= params["market_cap_max_yi"],
            valuation.code.in_(universe),
        )
        fund_df        = get_fundamentals_fn(q, date=prev_date)
        candidate_pool = (
            fund_df["code"].tolist()
            if (fund_df is not None and not fund_df.empty)
            else universe[:300]
        )
    except Exception:
        candidate_pool = universe[:300]

    if not candidate_pool:
        return pd.DataFrame()

    count = max(params["recent_limit_up_days"] + 5, 65)
    BATCH = 200

    all_price_data = {}
    for i in range(0, len(candidate_pool), BATCH):
        sub = candidate_pool[i: i + BATCH]
        try:
            prices = get_price_fn(
                sub, end_date=prev_date, count=count,
                frequency="daily",
                fields=["close", "high", "volume", "high_limit", "paused"],
                panel=False,
            )
            if prices is None or prices.empty:
                continue
            for stock in sub:
                df = prices[prices["code"] == stock].sort_index()
                if not df.empty:
                    all_price_data[stock] = df
        except Exception:
            continue

    candidates = []
    for stock in candidate_pool:
        df = all_price_data.get(stock)
        if df is None or len(df) < 10:
            continue
        result = _score_dip_from_df(stock, df, params)
        if result:
            candidates.append(result)

    if not candidates:
        return pd.DataFrame()

    return (
        pd.DataFrame(candidates)
        .sort_values("dip_score", ascending=False)
        .head(params["max_candidates"])
    )


def filter_momentum_candidates(universe, prev_date, params,
                               get_fundamentals_fn, get_price_fn, query_fn, valuation):
    """
    追涨候选池：昨日涨幅 > 3% + 换手率 > 3%

    参数：
      params: STRONG 或 WEAK_LATE_CHASE
    """
    turnover_min = params.get("min_turnover_rate", 0.03)
    try:
        q = query_fn(
            valuation.code,
            valuation.turnover_ratio,
        ).filter(
            valuation.turnover_ratio         >= turnover_min * 100,
            valuation.circulating_market_cap >= params["market_cap_min_yi"],
            valuation.circulating_market_cap <= params["market_cap_max_yi"],
            valuation.code.in_(universe),
        )
        fund_df        = get_fundamentals_fn(q, date=prev_date)
        candidate_pool = (
            fund_df["code"].tolist()
            if (fund_df is not None and not fund_df.empty)
            else universe[:300]
        )
    except Exception:
        candidate_pool = universe[:300]

    if not candidate_pool:
        return pd.DataFrame()

    BATCH          = 300
    all_price_data = {}
    for i in range(0, len(candidate_pool), BATCH):
        sub = candidate_pool[i: i + BATCH]
        try:
            prices = get_price_fn(
                sub, end_date=prev_date, count=3,
                frequency="daily", fields=["close", "paused"],
                panel=False,
            )
            if prices is None or prices.empty:
                continue
            for stock in sub:
                df = prices[prices["code"] == stock].sort_index()
                if not df.empty:
                    all_price_data[stock] = df
        except Exception:
            continue

    min_gain   = params.get("min_gain_prev_close", 0.03)
    candidates = []
    for stock in candidate_pool:
        df = all_price_data.get(stock)
        if df is None or len(df) < 2:
            continue
        if df["paused"].iloc[-1] == 1:
            continue
        prev_close  = df["close"].iloc[-2]
        today_close = df["close"].iloc[-1]
        if prev_close <= 0:
            continue
        gain = (today_close - prev_close) / prev_close
        if gain < min_gain:
            continue
        momentum_score = min(gain / 0.10, 1.0) * 100
        candidates.append({
            "stock":          stock,
            "close":          today_close,
            "today_gain_pct": round(gain * 100, 2),
            "momentum_score": round(momentum_score, 2),
        })

    if not candidates:
        return pd.DataFrame()

    return (
        pd.DataFrame(candidates)
        .sort_values("momentum_score", ascending=False)
        .head(params.get("max_candidates", 10))
    )


def _signals_from_dip(universe, prev_date, params, phase,
                      existing, total_value, phase_limit, max_stocks, current_count, batch_r,
                      jqdata_fns):
    """从低吸候选池生成买入信号"""
    candidates = filter_dip_candidates(universe, prev_date, params, **jqdata_fns)
    if candidates is None or candidates.empty:
        return []

    single_cap       = min(
        total_value * phase_limit / max_stocks,
        total_value * POSITION["max_single_stock_ratio"],
    )
    amount_per_stock = single_cap * batch_r
    signals          = []

    for _, row in candidates.iterrows():
        if len(signals) >= params["max_buy_count"]:
            break
        if current_count + len(signals) >= max_stocks:
            break
        stock = row["stock"]
        if stock in existing or amount_per_stock < 1000:
            continue
        reason = (
            f"[低吸/{PHASE_CN[phase]}] "
            f"回调{row.get('pullback_pct', 0):.1f}% "
            f"量缩{row.get('volume_shrink_pct', 0):.1f}%"
        )
        signals.append({
            "stock":  stock,
            "amount": amount_per_stock,
            "score":  row.get("dip_score", 0),
            "mode":   "DIP",
            "reason": reason,
        })
    return signals


def _signals_from_momentum(universe, prev_date, params, phase,
                           existing, total_value, phase_limit, max_stocks, current_count,
                           batch_r, max_buy, jqdata_fns):
    """从追涨候选池生成买入信号"""
    candidates = filter_momentum_candidates(universe, prev_date, params, **jqdata_fns)
    if candidates is None or candidates.empty:
        return []

    single_cap       = min(
        total_value * phase_limit / max_stocks,
        total_value * POSITION["max_single_stock_ratio"],
    )
    amount_per_stock = single_cap * batch_r
    signals          = []

    for _, row in candidates.iterrows():
        if len(signals) >= max_buy:
            break
        if current_count + len(signals) >= max_stocks:
            break
        stock = row["stock"]
        if stock in existing or amount_per_stock < 1000:
            continue
        reason = (
            f"[追涨/{PHASE_CN[phase]}] "
            f"昨涨{row.get('today_gain_pct', 0):.1f}%"
        )
        signals.append({
            "stock":  stock,
            "amount": amount_per_stock,
            "score":  row.get("momentum_score", 0),
            "mode":   "MOMENTUM",
            "reason": reason,
        })
    return signals


def generate_buy_signals(phase, universe, prev_date, market_regime,
                         total_value, current_count, cash, existing, jqdata_fns):
    """
    根据市场阶段生成买入信号

    参数：
      phase: 当前情绪阶段
      market_regime: 当前大盘趋势
      total_value: 组合总市值
      current_count: 当前持仓数量
      cash: 可用现金
      existing: 已持仓股票集合
      jqdata_fns: dict，含 get_fundamentals_fn/get_price_fn/query_fn/valuation

    返回：list of signal dict
    """
    regime_factor = REGIME_POSITION_FACTOR.get(market_regime, 1.0)
    phase_limit   = POSITION["max_position_by_phase"].get(phase, 0.20) * regime_factor
    phase_limit   = min(phase_limit, 1.0)
    max_stocks    = POSITION["max_stock_count"]

    used_ratio = 1 - cash / total_value if total_value > 0 else 1
    if used_ratio >= phase_limit - 0.05 or current_count >= max_stocks:
        return []

    dip_r   = POSITION["dip_batch_ratio"]
    chase_r = POSITION["momentum_batch_ratio"]

    common = dict(
        universe=universe, prev_date=prev_date, phase=phase,
        existing=existing, total_value=total_value,
        phase_limit=phase_limit, max_stocks=max_stocks,
        current_count=current_count, jqdata_fns=jqdata_fns,
    )

    if phase == PHASE_WEAK_EARLY:
        return _signals_from_dip(**common, params=WEAK_EARLY, batch_r=dip_r)

    elif phase == PHASE_WEAK_MID:
        return _signals_from_dip(**common, params=WEAK_MID, batch_r=dip_r)

    elif phase == PHASE_WEAK_LATE:
        dip_sigs = _signals_from_dip(**common, params=WEAK_LATE_DIP, batch_r=dip_r)
        existing_with_dip = existing | {s["stock"] for s in dip_sigs}
        chase_sigs = _signals_from_momentum(
            universe=universe, prev_date=prev_date, params=WEAK_LATE_CHASE,
            phase=phase, existing=existing_with_dip,
            total_value=total_value, phase_limit=phase_limit,
            max_stocks=max_stocks, current_count=current_count + len(dip_sigs),
            batch_r=chase_r, max_buy=WEAK_LATE_CHASE["max_buy_count"],
            jqdata_fns=jqdata_fns,
        )
        total_max = WEAK_LATE_DIP["max_buy_count"] + WEAK_LATE_CHASE["max_buy_count"]
        return (dip_sigs + chase_sigs)[:total_max]

    elif phase == PHASE_STRONG:
        return _signals_from_momentum(
            universe=universe, prev_date=prev_date, params=STRONG,
            phase=phase, existing=existing,
            total_value=total_value, phase_limit=phase_limit,
            max_stocks=max_stocks, current_count=current_count,
            batch_r=chase_r, max_buy=STRONG["max_buy_count"],
            jqdata_fns=jqdata_fns,
        )

    return []
