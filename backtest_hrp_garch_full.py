#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module: Backtest GJR-GARCH Tail Defense & HRP Capital Allocation (2020 - 2026)
==============================================================================
Kiểm định toàn diện 4 kịch bản qua 1,664 phiên (2020 - 2026):
1. Baseline: Quỹ Thực Chiến (ADX Choppy Adaptation + Fixed/Uptrend Sizing)
2. Layer A: Tích hợp GJR-GARCH Tail Risk Defense (Siết Trailing Stop khi phương sai bùng nổ)
3. Layer B: Tích hợp Hierarchical Risk Parity (HRP Dynamic Sizing)
4. Master Institutional: Full Combo (GJR-GARCH + HRP + Phái Sinh VN30F1M + ADX + Dynamic Slippage)
"""

import sys
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.spatial.distance import squareform
from scipy.cluster.hierarchy import linkage, fcluster
from sklearn.metrics import silhouette_score

from hrp_garch_engine import HierarchicalRiskParity, GarchTailRiskManager

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0.0)).rolling(window=period, min_periods=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)

def calculate_atr(high_df: pd.DataFrame, low_df: pd.DataFrame, close_df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    prev_close = close_df.shift(1)
    tr1 = high_df - low_df
    tr2 = (high_df - prev_close).abs()
    tr3 = (low_df - prev_close).abs()
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr

def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    up_move = high - prev_high
    down_move = prev_low - low
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    atr = tr.ewm(alpha=1.0/period, adjust=False).mean()
    pos_di = 100.0 * pd.Series(pos_dm, index=high.index).ewm(alpha=1.0/period, adjust=False).mean() / atr
    neg_di = 100.0 * pd.Series(neg_dm, index=high.index).ewm(alpha=1.0/period, adjust=False).mean() / atr
    
    dx = 100.0 * (pos_di - neg_di).abs() / (pos_di + neg_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1.0/period, adjust=False).mean()
    return adx.fillna(20.0)

# Load data
cache_vn30 = Path(r"C:\Users\X1 Yoga Gen 6\.gemini\antigravity\scratch\vn30_statistical_clustering\.cache\vn30_full_history_2020_2026.parquet")
cache_f1m = Path(r"C:\Users\X1 Yoga Gen 6\.gemini\antigravity\scratch\vn30_statistical_clustering\.cache\vn30f1m_2020_2026.parquet")

df_vn30 = pd.read_parquet(cache_vn30)
df_f1m = pd.read_parquet(cache_f1m)

close_cols = [c for c in df_vn30.columns if c.startswith('close_') and not c.startswith('close_VN30')]
high_cols = [c for c in df_vn30.columns if c.startswith('high_') and not c.startswith('high_VN30')]
low_cols = [c for c in df_vn30.columns if c.startswith('low_') and not c.startswith('low_VN30')]
vol_cols = [c for c in df_vn30.columns if c.startswith('volume_') and not c.startswith('volume_VN30')]

prices = df_vn30[close_cols].rename(columns=lambda c: c.replace('close_', '')).copy()
highs = df_vn30[high_cols].rename(columns=lambda c: c.replace('high_', '')).copy()
lows = df_vn30[low_cols].rename(columns=lambda c: c.replace('low_', '')).copy()
volumes = df_vn30[vol_cols].rename(columns=lambda c: c.replace('volume_', '')).copy()

for d in [prices, highs, lows]:
    for col in d.columns:
        d[col] = d[col].apply(lambda val: val * 1000.0 if (pd.notna(val) and val < 500.0) else val)

vn30_close = df_vn30['close_VN30'].ffill().bfill()
vn30_high = df_vn30['high_VN30'].ffill().bfill()
vn30_low = df_vn30['low_VN30'].ffill().bfill()

f1m_close = df_f1m['close'].reindex(prices.index).ffill().bfill()
f1m_vol = df_f1m['volume'].reindex(prices.index).fillna(0.0)
basis_spread = f1m_close - vn30_close

class HRPGarchBacktestEngine:
    def __init__(self, prices, highs, lows, volumes, vn30_c, vn30_h, vn30_l, basis_series, f1m_vol_series):
        self.prices = prices
        self.highs = highs
        self.lows = lows
        self.volumes = volumes
        self.vn30 = vn30_c
        self.basis = basis_series
        self.basis_2d = basis_series.rolling(window=2).mean()
        self.f1m_vol = f1m_vol_series
        
        self.symbols = prices.columns.tolist()
        self.dates = prices.index
        
        self.base_buy_fee = 0.0015
        self.base_sell_fee = 0.0025
        self.cash_daily_yield = 0.05 / 252.0
        
        self.vn30_ema20 = self.vn30.ewm(span=20, adjust=False).mean()
        self.vn30_rsi14 = calculate_rsi(self.vn30, period=14)
        self.vn30_adx14 = calculate_adx(vn30_h, vn30_l, vn30_c, period=14)
        
        self.sma_vol20 = self.volumes.rolling(window=20, min_periods=5).mean()
        self.rvol = (self.volumes / self.sma_vol20).fillna(0.0)
        self.rolling_high3 = self.highs.shift(1).rolling(window=3, min_periods=3).max()
        self.ema_10 = self.prices.ewm(span=10, adjust=False).mean()
        self.atr_14 = calculate_atr(self.highs, self.lows, self.prices, period=14)
        self.log_returns = np.log(self.prices / self.prices.shift(1)).fillna(0.0)

    def _cluster_and_hrp(self, current_idx: int, lookback: int = 90):
        window_returns = self.log_returns.iloc[current_idx - lookback : current_idx]
        cov_matrix = window_returns.cov()
        corr_matrix = window_returns.corr(method='pearson').fillna(0.0).values
        np.fill_diagonal(corr_matrix, 1.0)
        corr_matrix = (corr_matrix + corr_matrix.T) / 2.0
        
        dist_values = np.sqrt(np.clip(2.0 * (1.0 - corr_matrix), 0.0, 4.0))
        dist_values = (dist_values + dist_values.T) / 2.0
        np.fill_diagonal(dist_values, 0.0)
        dist_values = np.nan_to_num(dist_values, nan=0.0)
        
        condensed = squareform(dist_values, checks=False)
        linkage_z = linkage(condensed, method='ward')
        
        best_k = 4
        best_score = -2.0
        for k in range(3, 8):
            labels = fcluster(linkage_z, t=k, criterion='maxclust')
            if len(np.unique(labels)) > 1:
                score = silhouette_score(dist_values, labels, metric='precomputed')
                if score > best_score:
                    best_score = score
                    best_k = k
        final_labels = fcluster(linkage_z, t=best_k, criterion='maxclust')
        
        clusters = {}
        for s, lbl in zip(self.symbols, final_labels):
            clusters.setdefault(lbl, []).append(s)
            
        hrp_weights = HierarchicalRiskParity.compute_hrp_weights(cov_matrix, linkage_z)
        return clusters, hrp_weights

    def run_strategy(
        self,
        use_garch_defense: bool = True,
        use_hrp_sizing: bool = True,
        start_date: str = '2020-05-15',
        end_date: str = '2026-09-07'
    ):
        start_idx = self.dates.get_indexer([pd.Timestamp(start_date)], method='bfill')[0]
        end_idx = self.dates.get_indexer([pd.Timestamp(end_date)], method='ffill')[0]
        
        cash = 1_000_000_000.0
        positions = {}
        trade_history = []
        equity_records = []
        
        current_clusters = {}
        current_hrp_weights = pd.Series(1.0 / len(self.symbols), index=self.symbols)
        last_cluster_idx = -999
        cluster_rebalance_freq = 20
        vin_symbols = {'VIC', 'VHM', 'VRE', 'VPL'}
        
        for t in range(start_idx, end_idx + 1):
            curr_date = self.dates[t]
            curr_close = self.prices.iloc[t]
            curr_high = self.highs.iloc[t]
            curr_low = self.lows.iloc[t]
            curr_vol = self.volumes.iloc[t]
            prev_close = self.prices.iloc[t-1]
            
            cash += cash * self.cash_daily_yield
            
            if (t - last_cluster_idx) >= cluster_rebalance_freq or not current_clusters:
                current_clusters, current_hrp_weights = self._cluster_and_hrp(t, lookback=90)
                last_cluster_idx = t
                
            curr_adx = self.vn30_adx14.iloc[t]
            is_choppy = (curr_adx < 20.0)
            
            basis_val = self.basis.iloc[t]
            basis_2d_val = self.basis_2d.iloc[t]
            short_trap_alert = (basis_2d_val < -8.0 and curr_close.mean() > prev_close.mean())
            long_boost_alert = (basis_val > 5.0 and self.vn30.iloc[t] < self.vn30.iloc[t-1])
            
            # 1. Quản trị vị thế đang mở
            closed_symbols = []
            for sym, pos in positions.items():
                pos['holding_days'] += 1
                days = pos['holding_days']
                p_now = curr_close[sym]
                ret_from_entry = (p_now / pos['entry_price']) - 1.0
                p_atr = self.atr_14[sym].iloc[t]
                
                if curr_high[sym] > pos.get('high_peak', pos['entry_price']):
                    pos['high_peak'] = curr_high[sym]
                    
                exit_triggered = False
                exit_reason = ""
                
                # Dynamic Hard Stop-Loss (Choppy Adaptation)
                hard_sl = -0.055 if pos.get('was_choppy_entry', False) or is_choppy else -0.045
                if ret_from_entry <= hard_sl:
                    exit_triggered = True
                    exit_reason = f"Hard Stop-Loss ({hard_sl*100:.1f}%)"
                    
                # Dynamic Time Stop
                time_stop_day = 4 if pos.get('was_choppy_entry', False) or is_choppy else 3
                if not exit_triggered and days >= time_stop_day and pos['phase'] == 1:
                    if p_now <= pos['entry_price']:
                        exit_triggered = True
                        exit_reason = f"Time Stop T+{time_stop_day} (Không sinh lời)"
                        
                # Xét duyệt tại T+5
                if not exit_triggered and days == 5 and pos['phase'] == 1:
                    is_vin = (sym in vin_symbols)
                    threshold = 0.035 if is_vin else 0.040
                    if ret_from_entry >= threshold:
                        pos['phase'] = 2
                    else:
                        exit_triggered = True
                        exit_reason = f"Cycle Exit T+5 (+{ret_from_entry*100:.2f}% < Chuẩn Phase 2)"
                        
                # PHA 2: Chốt lời động kết hợp GJR-GARCH Tail Risk Defense
                if not exit_triggered and pos['phase'] == 2:
                    high_p = pos.get('high_peak', p_now)
                    
                    # Đánh giá GJR-GARCH Tail Risk
                    is_garch_tail_risk = False
                    if use_garch_defense:
                        sym_rets_slice = self.log_returns[sym].iloc[max(0, t-90):t]
                        is_garch_tail_risk, _, _ = GarchTailRiskManager.evaluate_tail_risk(sym_rets_slice)
                        
                    # Siết Trailing Stop nếu có cảnh báo GARCH hoặc Bẫy Phái sinh
                    if is_garch_tail_risk:
                        mult = 1.4  # GARCH bùng nổ biến động bất đối xứng: siết chặt về 1.4xATR
                        trail_reason_suffix = " (GARCH Tail Defense 1.4xATR)"
                    elif short_trap_alert:
                        mult = 1.5
                        trail_reason_suffix = " (Phái Sinh Short Basis 1.5xATR)"
                    else:
                        mult = 2.0
                        trail_reason_suffix = " (Tiêu Chuẩn 2.0xATR)"
                        
                    trailing_dist = mult * (p_atr if pd.notna(p_atr) else p_now * 0.02)
                    trail_stop_price = high_p - trailing_dist
                    
                    if p_now < trail_stop_price:
                        exit_triggered = True
                        exit_reason = f"Trailing Stop Phase 2{trail_reason_suffix}"
                    else:
                        p_ema10 = self.ema_10[sym].iloc[t]
                        p_rvol = self.rvol[sym].iloc[t]
                        if p_now < p_ema10 and p_now < prev_close[sym] and p_rvol > 1.2:
                            exit_triggered = True
                            exit_reason = "Dynamic Momentum Exit (Gãy EMA10 + Xả Vol lớn)"
                            
                if exit_triggered:
                    p_exit = p_now
                    adv20 = self.sma_vol20[sym].iloc[t]
                    slippage = 0.0010
                    if adv20 > 0:
                        sigma = self.log_returns[sym].iloc[t-20:t].std()
                        impact = 0.1 * sigma * np.sqrt(pos['shares'] / adv20)
                        slippage = max(0.0005, min(impact, 0.015))
                        
                    net_sell_price = p_exit * (1.0 - self.base_sell_fee - slippage)
                    proceeds = pos['shares'] * net_sell_price
                    cash += proceeds
                    closed_symbols.append(sym)
                    
                    cost = pos['cost_basis']
                    pnl = proceeds - cost
                    net_ret = (proceeds / cost - 1.0) * 100.0
                    trade_history.append({
                        'symbol': sym,
                        'entry_date': pos['entry_date'],
                        'exit_date': curr_date,
                        'holding_days': days,
                        'reason': exit_reason,
                        'net_pnl': round(pnl, 2),
                        'net_return_%': round(net_ret, 2),
                        'phase': f"Phase {pos['phase']}",
                        'tier': pos.get('tier', 'Tier 1')
                    })
                    
            for s in closed_symbols:
                del positions[s]
                
            # 2. Quét tín hiệu mở mới
            vn30_curr = self.vn30.iloc[t]
            vn30_ema = self.vn30_ema20.iloc[t]
            vn30_rsi = self.vn30_rsi14.iloc[t]
            vn30_uptrend = (vn30_curr > vn30_ema) and (45.0 <= vn30_rsi <= 75.0)
            
            cluster_vol_shares = {cid: sum(curr_vol[s] for s in syms if s in curr_vol) for cid, syms in current_clusters.items()}
            total_vn30_vol = sum(cluster_vol_shares.values())
            
            cluster_signals = {}
            for cid, syms in current_clusters.items():
                if any(s in positions for s in syms):
                    continue
                c_vol_now = cluster_vol_shares.get(cid, 0)
                c_vol_sma = sum(self.sma_vol20[s].iloc[t] for s in syms if s in self.sma_vol20 and pd.notna(self.sma_vol20[s].iloc[t]))
                cluster_rvol = (c_vol_now / c_vol_sma) if c_vol_sma > 0 else 0.0
                cluster_share = (c_vol_now / total_vn30_vol) if total_vn30_vol > 0 else 0.0
                
                candidates = []
                for s in syms:
                    if s in positions or curr_vol[s] <= 0 or pd.isna(curr_close[s]):
                        continue
                    s_rvol = self.rvol[s].iloc[t]
                    s_close = curr_close[s]
                    s_high = curr_high[s]
                    s_low = curr_low[s]
                    s_prev = prev_close[s]
                    s_pct_chg = (s_close / s_prev - 1.0) if s_prev > 0 else 0.0
                    
                    is_vin = (s in vin_symbols)
                    if is_vin:
                        vsa_candle = (s_close >= s_low + 0.50 * (s_high - s_low)) if (s_high > s_low) else False
                        rvol_cond = (s_rvol >= 1.3)
                        breakout_cond = (s_close > self.rolling_high3[s].iloc[t]) or (s_pct_chg >= 0.025)
                        base_signal = rvol_cond and vsa_candle and breakout_cond
                    else:
                        if not vn30_uptrend and not long_boost_alert:
                            continue
                        vsa_candle = (s_close >= s_low + 0.70 * (s_high - s_low)) if (s_high > s_low) else False
                        rvol_cond = (s_rvol >= 1.6)
                        breakout_cond = (s_close > self.rolling_high3[s].iloc[t])
                        base_signal = rvol_cond and vsa_candle and breakout_cond
                        
                    if base_signal:
                        is_tier2 = (cluster_rvol >= 2.0 and s_pct_chg >= 0.045 and cluster_share >= 0.28)
                        tier = "Tier 2" if is_tier2 else "Tier 1"
                        candidates.append({'symbol': s, 'rvol': s_rvol, 'tier': tier, 'pct_chg': s_pct_chg, 'is_t2': is_tier2})
                        
                if candidates:
                    candidates.sort(key=lambda x: (x['tier'] == 'Tier 2', x['rvol']), reverse=True)
                    cluster_signals[cid] = candidates[0]
                    
            # 3. Phân bổ vị thế mua mới (Tích hợp HRP Dynamic Allocation)
            if cluster_signals:
                tot_portfolio = sum(pos['shares'] * curr_close[s] for s, pos in positions.items())
                curr_nav = cash + tot_portfolio
                sorted_cids = sorted(cluster_signals.keys(), key=lambda c: (cluster_signals[c]['tier'] == 'Tier 2', cluster_signals[c]['rvol']), reverse=True)
                
                for cid in sorted_cids:
                    if len(positions) >= 5:
                        break
                    sig = cluster_signals[cid]
                    top_sym = sig['symbol']
                    
                    if use_hrp_sizing:
                        # Phân bổ tỷ trọng theo Hierarchical Risk Parity
                        target_pct = HierarchicalRiskParity.get_position_sizing(
                            sym=top_sym,
                            hrp_weights=current_hrp_weights,
                            num_symbols=len(self.symbols),
                            is_choppy=is_choppy,
                            is_uptrend=vn30_uptrend,
                            is_tier2=sig['is_t2']
                        )
                    else:
                        # Phân bổ theo heuristic cố định
                        if is_choppy:
                            target_pct = 0.20
                        else:
                            if vn30_uptrend:
                                target_pct = 0.35 if sig['tier'] == 'Tier 2' else 0.30
                            else:
                                target_pct = 0.20
                                
                    if short_trap_alert:
                        target_pct = min(target_pct, 0.20)
                        
                    alloc_val = curr_nav * target_pct
                    p_entry = curr_close[top_sym]
                    
                    adv20 = self.sma_vol20[top_sym].iloc[t]
                    est_shares = alloc_val / p_entry
                    slippage = 0.0010
                    if adv20 > 0:
                        sigma = self.log_returns[top_sym].iloc[t-20:t].std()
                        impact = 0.1 * sigma * np.sqrt(est_shares / adv20)
                        slippage = max(0.0005, min(impact, 0.015))
                        
                    net_entry_price = p_entry * (1.0 + self.base_buy_fee + slippage)
                    max_shares = int(alloc_val / net_entry_price / 100.0) * 100
                    if adv20 > 0:
                        max_shares = min(max_shares, int(adv20 * 0.05 / 100.0) * 100)
                        
                    cost = max_shares * net_entry_price
                    if max_shares > 0 and cash >= cost:
                        cash -= cost
                        positions[top_sym] = {
                            'entry_price': p_entry,
                            'net_entry_price': net_entry_price,
                            'entry_date': curr_date,
                            'entry_idx': t,
                            'shares': max_shares,
                            'cost_basis': cost,
                            'holding_days': 0,
                            'cluster_id': cid,
                            'high_peak': curr_high[top_sym],
                            'phase': 1,
                            'tier': sig['tier'],
                            'target_pct': target_pct,
                            'was_choppy_entry': is_choppy
                        }
                        
            tot_val = sum(pos['shares'] * curr_close[s] for s, pos in positions.items())
            nav = cash + tot_val
            equity_records.append({'date': curr_date, 'nav': nav})
            
        final_date = self.dates[end_idx]
        final_close = self.prices.iloc[end_idx]
        for sym, pos in list(positions.items()):
            shares = pos['shares']
            if shares > 0:
                p_exit = final_close[sym]
                net_p = p_exit * (1.0 - self.base_sell_fee - 0.0010)
                proc = shares * net_p
                cost = pos['cost_basis']
                holding = end_idx - pos['entry_idx']
                trade_history.append({
                    'symbol': sym,
                    'entry_date': pos['entry_date'],
                    'exit_date': final_date,
                    'holding_days': holding,
                    'reason': 'Chốt Cuối Kỳ Backtest (Mark-to-Market)',
                    'net_pnl': round(proc - cost, 2),
                    'net_return_%': round((proc / cost - 1.0) * 100.0, 2),
                    'phase': f"Phase {pos.get('phase', 1)}",
                    'tier': pos.get('tier', 'Tier 1')
                })
                
        eq_df = pd.DataFrame(equity_records).set_index('date')
        tr_df = pd.DataFrame(trade_history) if trade_history else pd.DataFrame()
        return eq_df, tr_df

def calculate_metrics(eq_df, tr_df, vn30_series, rf_annual=0.045):
    if eq_df.empty:
        return {}
    daily_rets = eq_df['nav'].pct_change().dropna()
    bench_rets = vn30_series.pct_change().dropna()
    common_idx = daily_rets.index.intersection(bench_rets.index)
    daily_rets = daily_rets.loc[common_idx]
    
    n_days = len(daily_rets)
    ann_factor = np.sqrt(252)
    rf_daily = rf_annual / 252.0
    
    tot_return = (eq_df['nav'].iloc[-1] / eq_df['nav'].iloc[0] - 1.0) * 100.0
    cummax = eq_df['nav'].cummax()
    dd = (eq_df['nav'] - cummax) / cummax
    mdd = abs(dd.min()) * 100.0
    cagr = ((eq_df['nav'].iloc[-1] / eq_df['nav'].iloc[0])**(252.0 / n_days) - 1.0) * 100.0 if n_days > 0 else 0.0
    
    mean_daily = daily_rets.mean()
    std_daily = daily_rets.std()
    ann_vol = std_daily * ann_factor * 100.0
    sharpe_zero = (mean_daily / std_daily) * ann_factor if std_daily > 0 else 0.0
    calmar = cagr / mdd if mdd > 0 else 0.0
    
    if not tr_df.empty and len(tr_df) > 0:
        win_trades = tr_df[tr_df['net_return_%'] > 0]
        wr = len(win_trades) / len(tr_df) * 100.0
        tot_win = win_trades['net_pnl'].sum()
        tot_loss = abs(tr_df[tr_df['net_return_%'] <= 0]['net_pnl'].sum())
        pf = (tot_win / tot_loss) if tot_loss > 0 else 99.0
        avg_hold = tr_df['holding_days'].mean()
    else:
        wr, pf, avg_hold = 0.0, 0.0, 0.0
        
    return {
        'Total_Return_%': round(tot_return, 2),
        'CAGR_%': round(cagr, 2),
        'Ann_Vol_%': round(ann_vol, 2),
        'MDD_%': round(mdd, 2),
        'Sharpe_Zero': round(sharpe_zero, 3),
        'Calmar_Ratio': round(calmar, 2),
        'Win_Rate_%': round(wr, 1),
        'Profit_Factor': round(pf, 2),
        'Avg_Holding_Days': round(avg_hold, 1),
        'Total_Trades': len(tr_df)
    }

def main():
    print("=== BẮT ĐẦU CHẠY KIỂM ĐỊNH 4 KỊCH BẢN GJR-GARCH & HRP (2020 - 2026) ===\n")
    engine = HRPGarchBacktestEngine(prices, highs, lows, volumes, vn30_close, vn30_high, vn30_low, basis_spread, f1m_vol)
    
    experiments = {
        '1. Baseline (Quỹ Thực Chiến + ADX Adaptation)': {
            'use_garch_defense': False, 'use_hrp_sizing': False
        },
        '2. Upgrade 1 (Tích Hợp GJR-GARCH Tail Defense)': {
            'use_garch_defense': True, 'use_hrp_sizing': False
        },
        '3. Upgrade 2 (Tích Hợp HRP Dynamic Sizing)': {
            'use_garch_defense': False, 'use_hrp_sizing': True
        },
        '4. Master Institutional (GJR-GARCH + HRP Full Combo)': {
            'use_garch_defense': True, 'use_hrp_sizing': True
        }
    }
    
    regimes = {
        'Full_Period_2020_2026': ('2020-05-15', '2026-09-07'),
        'Regime_1_Covid_Bull': ('2020-05-15', '2021-12-31'),
        'Regime_2_Bear_Market': ('2022-01-01', '2022-12-31'),
        'Regime_3_Recovery': ('2023-01-01', '2024-12-31'),
        'Regime_4_New_Era': ('2025-01-01', '2026-09-07')
    }
    
    all_summaries = {}
    all_equities = {}
    
    for name, params in experiments.items():
        print(f"--> Đang chạy mô phỏng: {name}...")
        eq, tr = engine.run_strategy(**params, start_date='2020-05-15', end_date='2026-09-07')
        all_equities[name] = eq['nav']
        
        reg_results = {}
        for r_k, (r_s, r_e) in regimes.items():
            eq_sub = eq.loc[r_s:r_e]
            tr_sub = tr[(tr['exit_date'] >= r_s) & (tr['exit_date'] <= r_e)] if not tr.empty else tr
            vn30_sub = engine.vn30.loc[r_s:r_e]
            reg_results[r_k] = calculate_metrics(eq_sub, tr_sub, vn30_sub)
            
        all_summaries[name] = reg_results
        
        m_full = reg_results['Full_Period_2020_2026']
        print(f"   [FULL] Return: {m_full['Total_Return_%']:+6.2f}% | MDD: {m_full['MDD_%']:5.2f}% | CAGR: {m_full['CAGR_%']:5.2f}% | Sharpe0: {m_full['Sharpe_Zero']:4.2f} | Calmar: {m_full['Calmar_Ratio']:4.2f} | PF: {m_full['Profit_Factor']:4.2f} | Trades: {m_full['Total_Trades']}")
        print(f"   [2022 BEAR] Return: {reg_results['Regime_2_Bear_Market']['Total_Return_%']:+6.2f}% | MDD: {reg_results['Regime_2_Bear_Market']['MDD_%']:.2f}%")
        print(f"   [2023-24 CHOP] Return: {reg_results['Regime_3_Recovery']['Total_Return_%']:+6.2f}% | MDD: {reg_results['Regime_3_Recovery']['MDD_%']:.2f}% | WR: {reg_results['Regime_3_Recovery']['Win_Rate_%']:.1f}%")
        print(f"   [2025-26 NEW ] Return: {reg_results['Regime_4_New_Era']['Total_Return_%']:+6.2f}% | MDD: {reg_results['Regime_4_New_Era']['MDD_%']:.2f}% | Sharpe: {reg_results['Regime_4_New_Era']['Sharpe_Zero']:.2f}\n")

    # Lưu json
    out_json = Path(r"C:\Users\X1 Yoga Gen 6\.gemini\antigravity\scratch\vn30_statistical_clustering\vn30_hrp_garch_summary.json")
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(all_summaries, f, indent=2, ensure_ascii=False)
        
    # Xuất chart
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 11), sharex=True, gridspec_kw={'height_ratios': [2.6, 1.3]})
    
    colors = ['#7f8c8d', '#2980b9', '#e67e22', '#27ae60']
    styles = ['--', '-', '-', '-']
    widths = [1.8, 2.2, 2.2, 2.6]
    
    for i, (name, nav_s) in enumerate(all_equities.items()):
        ret_val = all_summaries[name]['Full_Period_2020_2026']['Total_Return_%']
        mdd_val = all_summaries[name]['Full_Period_2020_2026']['MDD_%']
        lbl = f"{name} (Lãi: {ret_val:+.2f}%, MDD: -{mdd_val:.2f}%)"
        ax1.plot(nav_s.index, nav_s / 1e6, label=lbl, color=colors[i], linestyle=styles[i], linewidth=widths[i])
        
        dd_s = (nav_s - nav_s.cummax()) / nav_s.cummax() * 100.0
        ax2.plot(dd_s.index, dd_s, label=name.split(' (')[0], color=colors[i], linestyle=styles[i], linewidth=1.5)
        
    regime_dividers = [
        ('2022-01-01', 'Khủng Hoảng 2022'),
        ('2023-01-01', 'Phục Hồi 2023-2024'),
        ('2025-01-01', 'Kỷ Nguyên Mới 2025-2026')
    ]
    for date_str, reg_name in regime_dividers:
        t_stamp = pd.Timestamp(date_str)
        ax1.axvline(t_stamp, color='black', linestyle='--', linewidth=1.2, alpha=0.5)
        ax2.axvline(t_stamp, color='black', linestyle='--', linewidth=1.2, alpha=0.5)
        ax1.text(t_stamp + pd.Timedelta(days=5), ax1.get_ylim()[1]*0.95 if ax1.get_ylim()[1] else 1200, reg_name, fontsize=9, fontweight='bold', color='#2c3e50', alpha=0.8)

    ax1.set_title("ĐỐI CHIẾU HIỆU NĂNG GJR-GARCH TAIL DEFENSE & HIERARCHICAL RISK PARITY (HRP) (2020 - 2026)", fontsize=13, fontweight='bold', pad=12)
    ax1.set_ylabel("Tài Sản Ròng NAV (Triệu VNĐ)", fontsize=11, fontweight='bold')
    ax1.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.92, fontsize=10)
    
    ax2.set_ylabel("Mức Sụt Giảm (%)", fontsize=11, fontweight='bold')
    ax2.set_xlabel("Thời Gian Giao Dịch (2020 - 2026)", fontsize=11, fontweight='bold')
    ax2.legend(loc='lower left', frameon=True, facecolor='white', framealpha=0.92, fontsize=10)
    
    plt.tight_layout()
    chart_p = Path(r"C:\Users\X1 Yoga Gen 6\.gemini\antigravity\brain\61ebd816-c2de-4f34-9687-0ea8fda25f31\vn30_hrp_garch_comparison.png")
    fig.savefig(chart_p, dpi=300)
    print(f"\nĐã xuất biểu đồ so sánh HRP & GJR-GARCH tại: {chart_p}")

if __name__ == '__main__':
    main()
