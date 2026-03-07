# -*- coding: utf-8 -*-
"""
炒股养家情绪驱动策略
==========================================
策略名称：YouZi_EmotionDriven_v2
适用平台：聚宽（JoinQuant）回测

核心理念（严格对标炒股养家原文）：
  1. 每日判断市场是否存在「赚钱效应」或「亏钱效应」
  2. 亏钱效应（弱势市场）分三期：
       弱势初期 → 极轻仓低吸，止损更严（-5%）
       弱势中期 → 专注超跌股（更深回调 + 量缩至极）
       弱势末期 → 布局强势个股，可小仓位追涨
  3. 赚钱效应（强势市场）→ 追涨热点为主
  4. 过热高潮 → 不开新仓，持仓逐步减仓

使用方法：
  将本文件全部内容粘贴到聚宽策略编辑器中，设置回测时间后运行。

版本历史：
  v1.0 - 骨架搭建：情绪指数 + 低吸 + 追涨 + 仓位管理
  v1.1 - API修正：时序Bug修复、批量get_price、合并涨跌停查询
  v2.0 - 逻辑重构：严格对标炒股养家原文，弱势三阶段，各阶段独立参数
"""

from jqdata import *
import pandas as pd
import numpy as np


# ============================================================
# 市场阶段常量（对标炒股养家原文）
# ============================================================

PHASE_WEAK_EARLY = "WEAK_EARLY"  # 弱势初期：亏钱效应扩散，情绪持续恶化
PHASE_WEAK_MID   = "WEAK_MID"   # 弱势中期：低迷企稳，超跌股为主
PHASE_WEAK_LATE  = "WEAK_LATE"  # 弱势末期：情绪开始回升，布局强势
PHASE_STRONG     = "STRONG"     # 赚钱效应：追涨热点为主
PHASE_HOT        = "HOT"        # 过热高潮：分歧加大，只减仓不开新仓

PHASE_CN = {
    PHASE_WEAK_EARLY: "弱势初期",
    PHASE_WEAK_MID:   "弱势中期",
    PHASE_WEAK_LATE:  "弱势末期",
    PHASE_STRONG:     "赚钱效应",
    PHASE_HOT:        "过热高潮",
}


# ============================================================
# 策略参数
# ============================================================

# 情绪评分参数（对标养家原文描述的核心观察点）
EMOTION_PARAMS = {
    # 涨停打板次日赚钱效应（养家核心：打板者次日是否还能赚钱）
    "weight_next_day_effect": 0.40,
    # 涨停/跌停家数比（养家：涨停多=赚钱效应，跌停多=亏钱效应）
    "weight_limit_ratio":     0.30,
    # 大盘成交额趋势（养家：量能判断市场活跃度）
    "weight_volume_trend":    0.20,
    # 最高连板高度（辅助：量化游资活跃程度）
    "weight_max_boards":      0.10,

    # 强势/弱势分界
    "hot_threshold":    70,  # >= 70 → 过热
    "strong_threshold": 50,  # >= 50 → 赚钱效应；< 50 → 弱势三阶段

    # 弱势三阶段判断：当日分数 vs 近N日均值的差值
    "trend_window":  3,
    "trend_rising":  3.0,   # 差值 >  3 → 弱势末期（情绪回升）
    "trend_falling": -3.0,  # 差值 < -3 → 弱势初期（情绪恶化）
                            # 介于两者    → 弱势中期（情绪平稳）
}

# 各阶段总仓位上限
POSITION_PARAMS = {
    "max_position_by_phase": {
        PHASE_WEAK_EARLY: 0.20,  # 弱势初期：最多2成仓
        PHASE_WEAK_MID:   0.40,  # 弱势中期：最多4成仓
        PHASE_WEAK_LATE:  0.60,  # 弱势末期：最多6成仓
        PHASE_STRONG:     0.80,  # 赚钱效应：最多8成仓
        PHASE_HOT:        0.30,  # 过热：减至3成仓
    },
    "max_single_stock_ratio": 0.25,  # 单股不超总资产25%
    "max_stock_count":        4,     # 最多同时持4只
    "dip_batch_ratio":        0.333, # 低吸建仓：1/3仓
    "momentum_batch_ratio":   0.50,  # 追涨建仓：1/2仓
}

# ── 弱势初期：极轻仓低吸，快速止损 ──────────────────────────
WEAK_EARLY_PARAMS = {
    "recent_limit_up_days":   20,
    "pullback_from_high_min": 0.20,   # 回调 >= 20%（更深才值得低吸）
    "volume_shrink_days":     5,
    "volume_shrink_ratio":    0.50,   # 量缩至5日均量50%以下
    "trend_ma_period":        60,
    "price_above_ma_ratio":   0.80,
    "market_cap_min_yi":      10,
    "market_cap_max_yi":      200,
    "max_candidates":         10,
    "max_buy_count":          1,      # 最多只买1只（试探仓）
    "stop_loss":              -0.05,  # 快速止损：-5%
}

# ── 弱势中期：专注超跌，标准止损 ─────────────────────────────
WEAK_MID_PARAMS = {
    "recent_limit_up_days":   30,
    "pullback_from_high_min": 0.25,   # 回调 >= 25%（超跌）
    "volume_shrink_days":     5,
    "volume_shrink_ratio":    0.45,   # 量缩更极致
    "trend_ma_period":        60,
    "price_above_ma_ratio":   0.75,   # 允许离均线更远
    "market_cap_min_yi":      10,
    "market_cap_max_yi":      200,
    "max_candidates":         15,
    "max_buy_count":          2,
    "stop_loss":              -0.07,
}

# ── 弱势末期低吸部分：要求放宽，可布局强势个股 ───────────────
WEAK_LATE_DIP_PARAMS = {
    "recent_limit_up_days":   20,
    "pullback_from_high_min": 0.15,   # 回调要求放宽
    "volume_shrink_days":     5,
    "volume_shrink_ratio":    0.60,
    "trend_ma_period":        60,
    "price_above_ma_ratio":   0.80,
    "market_cap_min_yi":      10,
    "market_cap_max_yi":      300,
    "max_candidates":         20,
    "max_buy_count":          2,
    "stop_loss":              -0.07,
}

# ── 弱势末期追涨部分：开始出现的强势个股 ────────────────────
WEAK_LATE_CHASE_PARAMS = {
    "min_gain_prev_close":  0.03,    # 昨日涨幅 > 3%
    "min_turnover_rate":    0.03,    # 换手率 > 3%
    "market_cap_min_yi":    10,
    "market_cap_max_yi":    300,
    "max_candidates":       10,
    "max_buy_count":        1,       # 弱势末期追涨最多1只
    "stop_loss":            -0.07,
}

# ── 赚钱效应：追涨热点为主 ────────────────────────────────────
STRONG_PARAMS = {
    "min_gain_prev_close":  0.03,    # 昨日涨幅 > 3%
    "min_turnover_rate":    0.03,    # 换手率 > 3%
    "market_cap_min_yi":    10,
    "market_cap_max_yi":    500,
    "max_candidates":       10,
    "max_buy_count":        2,
    "stop_loss":            -0.07,
}

# 通用止盈参数
EXIT_PARAMS = {
    "profit_protect_trigger":  0.15,  # 浮盈 > 15% 后启动保护
    "profit_protect_drawdown": 0.07,  # 从峰值回撤 7% 止盈
    "hot_reduce_trigger":      0.05,  # 过热浮盈 > 5% 减半仓
    "max_hold_days":           10,    # 持仓超10天未走强清仓
    "timeout_min_gain":        0.02,  # 超时清仓的盈亏门槛
}


def _get_stop_loss(phase):
    """获取当前阶段的止损比例（弱势初期更严格）"""
    return {
        PHASE_WEAK_EARLY: WEAK_EARLY_PARAMS["stop_loss"],
        PHASE_WEAK_MID:   WEAK_MID_PARAMS["stop_loss"],
        PHASE_WEAK_LATE:  WEAK_LATE_DIP_PARAMS["stop_loss"],
        PHASE_STRONG:     STRONG_PARAMS["stop_loss"],
        PHASE_HOT:        -0.07,
    }.get(phase, -0.07)


# ============================================================
# 聚宽策略入口函数
# ============================================================

def initialize(context):
    """策略初始化（回测开始时调用一次）"""
    set_benchmark("000300.XSHG")
    set_option("use_real_price", True)
    set_order_cost(
        OrderCost(
            open_tax=0,
            close_tax=0.001,
            open_commission=0.0003,
            close_commission=0.0003,
            close_today_commission=0,
            min_commission=5,
        ),
        type="stock",
    )
    set_slippage(PriceRelatedSlippage(0.002), type="stock")

    context.emotion_records  = []            # [(date_str, score, phase), ...]
    context.emotion_phase    = PHASE_WEAK_MID
    context.emotion_score    = 40.0
    context.position_records = {}            # {stock: {max_price, hold_days, entry_date}}
    context.buy_signals      = []
    context.sell_signals     = []
    context.verbose          = True

    run_daily(execute_trades, time="open")
    log.info("=== YouZi_EmotionDriven_v2 初始化完成 ===")


def before_trading_start(context):
    """
    每日开盘前（9:00）计算情绪、生成信号
    重要：此时今日市场未开，只能访问 context.previous_date 及之前的数据。
    """
    prev_date  = context.previous_date
    trade_days = get_trade_days(end_date=prev_date, count=2)
    if len(trade_days) < 2:
        return
    prev2_date = trade_days[0]

    # ── Step 1: 计算昨日市场情绪评分 ──────────────────────────
    lu_list, lu_cnt, ld_cnt = _get_market_limit_data(prev_date)
    score = _calc_emotion_score(
        date=prev_date, prev2_date=prev2_date,
        lu_list=lu_list, lu_cnt=lu_cnt, ld_cnt=ld_cnt,
    )
    score_history = [r[1] for r in context.emotion_records]
    phase         = _classify_phase(score, score_history)

    prev_phase            = context.emotion_phase
    context.emotion_phase = phase
    context.emotion_score = score
    context.emotion_records.append((str(prev_date), score, phase))
    if len(context.emotion_records) > 30:
        context.emotion_records.pop(0)

    phase_idx = list(PHASE_CN.keys()).index(phase)
    record(emotion_score=score, emotion_phase=phase_idx)

    if context.verbose:
        log.info(
            f"[情绪] 基于{prev_date} | 评分={score:.1f} | "
            f"阶段={PHASE_CN.get(phase, phase)}"
            f"{' ←切换!' if phase != prev_phase else ''} | "
            f"涨停={lu_cnt} 跌停={ld_cnt}"
        )

    # ── Step 2: 卖出信号（优先执行）─────────────────────────
    context.sell_signals = _generate_sell_signals(context)

    # ── Step 3: 买入信号 ─────────────────────────────────────
    if phase == PHASE_HOT:
        context.buy_signals = []
        if context.verbose:
            log.info("[信号] 过热高潮，暂停开新仓")
    else:
        universe = _get_universe(prev_date)
        context.buy_signals = _generate_buy_signals(
            context, universe, prev_date, phase
        )

    if context.verbose:
        log.info(
            f"[信号] 卖出={len(context.sell_signals)}只  "
            f"买入={len(context.buy_signals)}只"
        )


def execute_trades(context):
    """每日开盘（9:30）先卖后买"""
    for sig in context.sell_signals:
        stock = sig["stock"]
        if stock not in context.portfolio.positions:
            continue
        if sig["ratio"] >= 1.0:
            order_target_value(stock, 0)
            if context.verbose:
                log.info(
                    f"[卖出] {stock} 全仓 | {sig['reason']} | "
                    f"盈亏={sig['gain_pct']:.1f}%"
                )
        else:
            current_val = context.portfolio.positions[stock].value
            order_target_value(stock, current_val * (1 - sig["ratio"]))
            if context.verbose:
                log.info(
                    f"[减仓] {stock} -{sig['ratio']*100:.0f}% | {sig['reason']}"
                )

    for sig in context.buy_signals:
        stock  = sig["stock"]
        amount = min(sig["amount"], context.portfolio.cash * 0.95)
        if amount < 1000:
            continue
        order_value(stock, amount)
        if context.verbose:
            log.info(f"[买入] {stock} {amount:.0f}元 | {sig['reason']}")

    _update_position_records(context)


# ============================================================
# 情绪指数计算
# ============================================================

def _get_market_limit_data(date):
    """
    批量查询指定日期涨停/跌停数据
    返回：(lu_list, lu_count, ld_count)
    """
    stocks = _get_universe(date)
    if not stocks:
        return [], 0, 0

    lu_list  = []
    ld_count = 0
    BATCH    = 500

    for i in range(0, len(stocks), BATCH):
        sub = stocks[i: i + BATCH]
        try:
            prices = get_price(
                sub, start_date=date, end_date=date,
                frequency="daily",
                fields=["close", "high_limit", "low_limit"],
                skip_paused=True, panel=False,
            )
            if prices is None or prices.empty:
                continue
            if "code" in prices.columns:
                lu_rows = prices[prices["close"] >= prices["high_limit"] * 0.999]
                ld_rows = prices[prices["close"] <= prices["low_limit"]  * 1.001]
                lu_list.extend(lu_rows["code"].tolist())
                ld_count += len(ld_rows)
        except Exception:
            continue

    return lu_list, len(lu_list), ld_count


def _calc_emotion_score(date, prev2_date, lu_list, lu_cnt, ld_cnt):
    """
    计算综合情绪评分（0-100）

    养家核心观察点：
      1. 打板次日赚钱效应 —— 最核心，判断赚钱/亏钱效应
      2. 涨停/跌停比      —— 市场多空力量对比
      3. 大盘成交额趋势   —— 量能判断市场活跃度
      4. 最高连板高度     —— 辅助：游资活跃程度
    """
    ep = EMOTION_PARAMS

    # 指标1：涨停打板次日赚钱效应（T-2涨停股在T-1的平均表现）
    next_day_effect = _limit_up_next_day_effect(prev2_date, date)
    s_effect = _normalize(next_day_effect, -0.05, 0.05)

    # 指标2：涨停/跌停家数比
    total   = lu_cnt + ld_cnt
    ratio   = lu_cnt / total if total > 0 else 0.5
    s_ratio = _normalize(ratio, 0.3, 0.7)

    # 指标3：大盘成交额趋势
    vol_trend = _market_volume_trend(date)
    s_vol     = _normalize(vol_trend, -0.2, 0.2)

    # 指标4：最高连板高度（辅助）
    max_boards = _max_consecutive_boards(date, lu_list)
    s_boards   = _normalize(max_boards, 0, 8)

    score = (
        s_effect * ep["weight_next_day_effect"] +
        s_ratio  * ep["weight_limit_ratio"]     +
        s_vol    * ep["weight_volume_trend"]     +
        s_boards * ep["weight_max_boards"]
    ) * 100

    return round(float(np.clip(score, 0, 100)), 2)


def _limit_up_next_day_effect(prev2_date, prev_date):
    """
    涨停打板次日赚钱效应：T-2涨停股在T-1的平均涨幅
    正值 → 赚钱效应；负值 → 亏钱效应
    """
    lu_stocks, _, _ = _get_market_limit_data(prev2_date)
    if not lu_stocks:
        return 0.0
    try:
        prices = get_price(
            lu_stocks,
            start_date=prev_date, end_date=prev_date,
            frequency="daily", fields=["open", "close"],
            skip_paused=True, panel=False,
        )
        if prices is None or prices.empty:
            return 0.0
        prices["pct"] = (prices["close"] - prices["open"]) / prices["open"]
        return float(prices["pct"].mean())
    except Exception:
        return 0.0


def _market_volume_trend(date, window=5):
    """大盘成交额趋势：当日 vs 前N日均值"""
    try:
        sh = get_price("000001.XSHG", end_date=date, count=window + 1,
                       fields=["money"], frequency="daily")
        sz = get_price("399001.XSHE", end_date=date, count=window + 1,
                       fields=["money"], frequency="daily")
        if sh is None or sz is None or sh.empty or sz.empty:
            return 0.0
        total  = sh["money"].values + sz["money"].values
        recent = float(total[-1])
        avg    = float(np.mean(total[:-1]))
        return (recent - avg) / avg if avg > 0 else 0.0
    except Exception:
        return 0.0


def _max_consecutive_boards(date, lu_list, sample_size=40):
    """最高连板高度（辅助指标，抽样计算）"""
    if not lu_list:
        return 0
    sample     = lu_list[:sample_size]
    trade_days = get_trade_days(end_date=date, count=15)
    if not len(trade_days):
        return 1
    try:
        all_prices = get_price(
            sample,
            start_date=trade_days[0], end_date=date,
            frequency="daily", fields=["close", "high_limit"],
            panel=False,
        )
        if all_prices is None or all_prices.empty:
            return 1
    except Exception:
        return 1

    max_boards = 1
    for stock in sample:
        df = all_prices[all_prices["code"] == stock].sort_index()
        if df.empty:
            continue
        is_lu = (df["close"] >= df["high_limit"] * 0.999).tolist()
        cnt   = 0
        for v in reversed(is_lu):
            if v:
                cnt += 1
            else:
                break
        max_boards = max(max_boards, cnt)
    return max_boards


def _classify_phase(score, score_history):
    """
    五阶段分类（对标炒股养家原文）

    强势/弱势由分数绝对值决定：
      >= hot_threshold    → 过热
      >= strong_threshold → 赚钱效应（STRONG）
      < strong_threshold  → 弱势区间

    弱势三阶段由近N日趋势方向决定：
      情绪回升  → 弱势末期（末期布局）
      情绪恶化  → 弱势初期（轻仓止损）
      情绪平稳  → 弱势中期（超跌为主）
    """
    ep = EMOTION_PARAMS

    if score >= ep["hot_threshold"]:
        return PHASE_HOT
    if score >= ep["strong_threshold"]:
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


# ============================================================
# 股票池构建
# ============================================================

def _get_universe(date):
    """基础股票池：过滤ST、次新股（上市不足365天）"""
    try:
        sec    = get_all_securities(types=["stock"], date=date)
        cutoff = pd.Timestamp(date) - pd.Timedelta(days=365)
        sec    = sec[sec["start_date"] <= cutoff.date()]
        sec    = sec[~sec["display_name"].str.contains("ST", na=False)]
        return sec.index.tolist()
    except Exception:
        return []


# ============================================================
# 低吸候选股筛选（弱势初期/中期/末期共用，参数各异）
# ============================================================

def _filter_dip_candidates(universe, prev_date, params):
    """
    低吸候选池筛选（批量化 get_price）
    params 传入对应阶段的参数字典（WEAK_EARLY/MID/LATE_DIP_PARAMS）

    筛选条件（AND逻辑）：
      1. 近N天内有涨停记录
      2. 从近期高点回调 >= 阶段设定值
      3. 成交量缩至N日均量的X%以下
      4. 收盘价不低于60日均线的X%
    """
    try:
        q = query(valuation.code).filter(
            valuation.circulating_market_cap >= params["market_cap_min_yi"],
            valuation.circulating_market_cap <= params["market_cap_max_yi"],
            valuation.code.in_(universe),
        )
        fund_df        = get_fundamentals(q, date=prev_date)
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
            prices = get_price(
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


def _score_dip_from_df(stock, prices, p):
    """计算低吸评分（无API调用，基于预取数据）"""
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

    # 评分
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


# ============================================================
# 追涨候选股筛选（STRONG / WEAK_LATE 追涨部分）
# ============================================================

def _filter_momentum_candidates(universe, prev_date, params):
    """
    追涨候选池：昨日涨幅 > 3% + 换手率 > 3%
    params 传入 STRONG_PARAMS 或 WEAK_LATE_CHASE_PARAMS
    """
    turnover_min = params.get("min_turnover_rate", 0.03)
    try:
        q = query(
            valuation.code,
            valuation.turnover_ratio,
        ).filter(
            valuation.turnover_ratio         >= turnover_min * 100,
            valuation.circulating_market_cap >= params["market_cap_min_yi"],
            valuation.circulating_market_cap <= params["market_cap_max_yi"],
            valuation.code.in_(universe),
        )
        fund_df        = get_fundamentals(q, date=prev_date)
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
            prices = get_price(
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


# ============================================================
# 信号生成
# ============================================================

def _generate_buy_signals(context, universe, prev_date, phase):
    """
    根据市场阶段生成买入信号（养家五阶段操作逻辑）

    弱势初期：极轻仓低吸，只买1只，快速止损
    弱势中期：专注超跌，最多2只
    弱势末期：低吸为主 + 小仓追涨，最多3只
    赚钱效应：追涨热点，最多2只
    过热高潮：不买（由调用方过滤）
    """
    total_value   = context.portfolio.total_value
    current_count = len(context.portfolio.positions)
    existing      = set(context.portfolio.positions.keys())
    phase_limit   = POSITION_PARAMS["max_position_by_phase"].get(phase, 0.20)
    max_stocks    = POSITION_PARAMS["max_stock_count"]

    used_ratio = 1 - context.portfolio.cash / total_value if total_value > 0 else 1
    if used_ratio >= phase_limit - 0.05 or current_count >= max_stocks:
        return []

    if phase == PHASE_WEAK_EARLY:
        return _signals_from_dip(
            universe, prev_date, WEAK_EARLY_PARAMS,
            phase, existing, total_value, phase_limit, max_stocks, current_count,
            batch_r=POSITION_PARAMS["dip_batch_ratio"],
        )

    elif phase == PHASE_WEAK_MID:
        return _signals_from_dip(
            universe, prev_date, WEAK_MID_PARAMS,
            phase, existing, total_value, phase_limit, max_stocks, current_count,
            batch_r=POSITION_PARAMS["dip_batch_ratio"],
        )

    elif phase == PHASE_WEAK_LATE:
        # 低吸为主
        dip_sigs = _signals_from_dip(
            universe, prev_date, WEAK_LATE_DIP_PARAMS,
            phase, existing, total_value, phase_limit, max_stocks, current_count,
            batch_r=POSITION_PARAMS["dip_batch_ratio"],
        )
        # 追涨为辅（不超过1只，且不重复已选股）
        existing_with_dip = existing | {s["stock"] for s in dip_sigs}
        chase_sigs = _signals_from_momentum(
            universe, prev_date, WEAK_LATE_CHASE_PARAMS,
            phase, existing_with_dip, total_value, phase_limit, max_stocks,
            current_count + len(dip_sigs),
            batch_r=POSITION_PARAMS["momentum_batch_ratio"],
            max_buy=WEAK_LATE_CHASE_PARAMS["max_buy_count"],
        )
        total_max = WEAK_LATE_DIP_PARAMS["max_buy_count"] + WEAK_LATE_CHASE_PARAMS["max_buy_count"]
        return (dip_sigs + chase_sigs)[:total_max]

    elif phase == PHASE_STRONG:
        return _signals_from_momentum(
            universe, prev_date, STRONG_PARAMS,
            phase, existing, total_value, phase_limit, max_stocks, current_count,
            batch_r=POSITION_PARAMS["momentum_batch_ratio"],
            max_buy=STRONG_PARAMS["max_buy_count"],
        )

    return []


def _signals_from_dip(
    universe, prev_date, params, phase,
    existing, total_value, phase_limit, max_stocks, current_count, batch_r,
):
    """从低吸候选池生成买入信号"""
    candidates = _filter_dip_candidates(universe, prev_date, params)
    if candidates is None or candidates.empty:
        return []

    single_cap       = min(
        total_value * phase_limit / max_stocks,
        total_value * POSITION_PARAMS["max_single_stock_ratio"],
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


def _signals_from_momentum(
    universe, prev_date, params, phase,
    existing, total_value, phase_limit, max_stocks, current_count,
    batch_r, max_buy,
):
    """从追涨候选池生成买入信号"""
    candidates = _filter_momentum_candidates(universe, prev_date, params)
    if candidates is None or candidates.empty:
        return []

    single_cap       = min(
        total_value * phase_limit / max_stocks,
        total_value * POSITION_PARAMS["max_single_stock_ratio"],
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


def _generate_sell_signals(context):
    """
    卖出信号（养家原文：止损优先，浮盈保护，过热减仓）

    弱势初期止损更严格（-5%），其余阶段-7%
    """
    signals   = []
    phase     = context.emotion_phase
    pos_recs  = context.position_records
    ep        = EXIT_PARAMS
    stop_loss = _get_stop_loss(phase)

    for stock, pos in context.portfolio.positions.items():
        try:
            entry   = pos.avg_cost
            current = pos.price
            rec     = pos_recs.get(stock, {})
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


# ============================================================
# 持仓记录管理
# ============================================================

def _update_position_records(context):
    """维护持仓最高价和持仓天数"""
    if not hasattr(context, "position_records"):
        context.position_records = {}

    for stock, pos in context.portfolio.positions.items():
        price = pos.price
        if stock not in context.position_records:
            context.position_records[stock] = {
                "max_price":  price,
                "hold_days":  1,
                "entry_date": str(context.current_dt.date()),
            }
        else:
            rec = context.position_records[stock]
            rec["hold_days"] += 1
            if price > rec["max_price"]:
                rec["max_price"] = price

    current_stocks = set(context.portfolio.positions.keys())
    for s in list(context.position_records.keys()):
        if s not in current_stocks:
            del context.position_records[s]


# ============================================================
# 工具函数
# ============================================================

def _normalize(value, low, high):
    """线性归一化到 [0, 1]"""
    if high == low:
        return 0.5
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))
