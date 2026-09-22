#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module: Compare Quantitative Strategy with VN-INDEX Benchmark (2020 - 2026)
=============================================================================
So sánh chi tiết hiệu năng giữa các cấu hình chiến lược và VN-Index:
- VN-Index Buy & Hold
- VN30 Index Buy & Hold
- Baseline (Quỹ Thực Chiến + ADX)
- Upgrade 1 (GJR-GARCH Tail Defense)
- Upgrade 2 (HRP Dynamic Sizing)
- Master Institutional (GARCH + HRP Full Combo)

Tính toán: Alpha, Beta, Information Ratio, Sharpe, Calmar, Max Drawdown và phân kỳ chu kỳ.
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

# Thêm đường dẫn project
sys.path.insert(0, r"C:\Users\X1 Yoga Gen 6\.gemini\antigravity\scratch\vn30_statistical_clustering")

from backtest_hrp_garch_full import (
    HRPGarchBacktestEngine,
    prices, highs, lows, volumes,
    vn30_close, vn30_high, vn30_low,
    basis_spread, f1m_vol,
    calculate_metrics
)

CACHE_DIR = Path(r"C:\Users\X1 Yoga Gen 6\.gemini\antigravity\scratch\vn30_statistical_clustering\.cache")
df_vnindex = pd.read_parquet(CACHE_DIR / "vnindex_2020_2026.parquet")
vnindex_close = df_vnindex['close'].reindex(prices.index).ffill().bfill()

def calc_benchmark_metrics(index_series, start_date='2020-05-15', end_date='2026-09-07'):
    sub = index_series.loc[start_date:end_date]
    daily_rets = sub.pct_change().dropna()
    n_days = len(daily_rets)
    ann_factor = np.sqrt(252)
    
    tot_return = (sub.iloc[-1] / sub.iloc[0] - 1.0) * 100.0
    cagr = ((sub.iloc[-1] / sub.iloc[0])**(252.0 / n_days) - 1.0) * 100.0 if n_days > 0 else 0.0
    
    cummax = sub.cummax()
    dd = (sub - cummax) / cummax
    mdd = abs(dd.min()) * 100.0
    
    std_daily = daily_rets.std()
    mean_daily = daily_rets.mean()
    ann_vol = std_daily * ann_factor * 100.0
    sharpe = (mean_daily / std_daily) * ann_factor if std_daily > 0 else 0.0
    calmar = cagr / mdd if mdd > 0 else 0.0
    
    return {
        'Total_Return_%': round(tot_return, 2),
        'CAGR_%': round(cagr, 2),
        'Ann_Vol_%': round(ann_vol, 2),
        'MDD_%': round(mdd, 2),
        'Sharpe_Zero': round(sharpe, 3),
        'Calmar_Ratio': round(calmar, 2)
    }

def calc_relative_metrics(strat_series, bench_series):
    s_ret = strat_series.pct_change().dropna()
    b_ret = bench_series.pct_change().dropna()
    common = s_ret.index.intersection(b_ret.index)
    s_ret, b_ret = s_ret.loc[common], b_ret.loc[common]
    
    ann_factor = np.sqrt(252)
    cov_sb = np.cov(s_ret, b_ret)[0, 1]
    var_b = np.var(b_ret)
    beta = cov_sb / var_b if var_b > 0 else 1.0
    corr = np.corrcoef(s_ret, b_ret)[0, 1]
    
    ann_strat_ret = s_ret.mean() * 252.0
    ann_bench_ret = b_ret.mean() * 252.0
    alpha = (ann_strat_ret - beta * ann_bench_ret) * 100.0
    
    diff_ret = s_ret - b_ret
    te = diff_ret.std() * ann_factor * 100.0
    ir = (diff_ret.mean() * 252.0 * 100.0) / te if te > 0 else 0.0
    
    return {
        'Alpha_%': round(alpha, 2),
        'Beta': round(beta, 3),
        'Correlation': round(corr, 3),
        'Tracking_Error_%': round(te, 2),
        'Information_Ratio': round(ir, 2)
    }

def main():
    print("=== BẮT ĐẦU CHẠY PHÂN TÍCH SO SÁNH VỚI VN-INDEX (2020 - 2026) ===")
    
    engine = HRPGarchBacktestEngine(prices, highs, lows, volumes, vn30_close, vn30_high, vn30_low, basis_spread, f1m_vol)
    
    configs = {
        '1. Baseline (Quỹ + ADX)': {'use_garch_defense': False, 'use_hrp_sizing': False},
        '2. GJR-GARCH Tail Defense': {'use_garch_defense': True, 'use_hrp_sizing': False},
        '3. HRP Dynamic Sizing': {'use_garch_defense': False, 'use_hrp_sizing': True},
        '4. Master Combo (GARCH + HRP)': {'use_garch_defense': True, 'use_hrp_sizing': True}
    }
    
    regimes = {
        'Full_Period_2020_2026': ('2020-05-15', '2026-09-07'),
        'Regime_1_Covid_Bull': ('2020-05-15', '2021-12-31'),
        'Regime_2_Bear_Market': ('2022-01-01', '2022-12-31'),
        'Regime_3_Recovery': ('2023-01-01', '2024-12-31'),
        'Regime_4_New_Era': ('2025-01-01', '2026-09-07')
    }
    
    strat_equities = {}
    strat_summaries = {}
    
    for cname, cparams in configs.items():
        print(f"Chạy backtest: {cname}...")
        eq, tr = engine.run_strategy(**cparams, start_date='2020-05-15', end_date='2026-09-07')
        strat_equities[cname] = eq['nav']
        
        reg_res = {}
        for rname, (rs, re) in regimes.items():
            eq_sub = eq.loc[rs:re]
            tr_sub = tr[(tr['exit_date'] >= rs) & (tr['exit_date'] <= re)] if not tr.empty else tr
            reg_res[rname] = calculate_metrics(eq_sub, tr_sub, vnindex_close.loc[rs:re])
            # Thêm alpha, beta so với VN-Index
            rel = calc_relative_metrics(eq_sub['nav'], vnindex_close.loc[rs:re])
            reg_res[rname].update(rel)
            
        strat_summaries[cname] = reg_res
        
    # Tính metrics cho VN-Index và VN30 Index
    vnindex_summaries = {}
    vn30_summaries = {}
    for rname, (rs, re) in regimes.items():
        vnindex_summaries[rname] = calc_benchmark_metrics(vnindex_close, rs, re)
        vn30_summaries[rname] = calc_benchmark_metrics(vn30_close, rs, re)
        
    full_report = {
        'VNINDEX': vnindex_summaries,
        'VN30': vn30_summaries,
        'Strategies': strat_summaries
    }
    
    # In báo cáo tóm tắt
    print("\n" + "="*95)
    print("BẢNG TỔNG HỢP SO SÁNH TOÀN DIỆN VỚI VN-INDEX & VN30 (2020 - 2026):")
    print("="*95)
    header = f"{'Chỉ Số / Tài Sản':<30} | {'VN-INDEX':<10} | {'VN30 INDEX':<10} | {'Baseline':<10} | {'HRP Sizing':<10} | {'Master Combo':<10}"
    print(header)
    print("-"*95)
    
    full_idx = 'Full_Period_2020_2026'
    vni_m = vnindex_summaries[full_idx]
    v30_m = vn30_summaries[full_idx]
    b_m = strat_summaries['1. Baseline (Quỹ + ADX)'][full_idx]
    hrp_m = strat_summaries['3. HRP Dynamic Sizing'][full_idx]
    mas_m = strat_summaries['4. Master Combo (GARCH + HRP)'][full_idx]
    
    rows = [
        ("Tổng Lợi Nhuận (%)", f"{vni_m['Total_Return_%']:+.2f}%", f"{v30_m['Total_Return_%']:+.2f}%", f"{b_m['Total_Return_%']:+.2f}%", f"{hrp_m['Total_Return_%']:+.2f}%", f"{mas_m['Total_Return_%']:+.2f}%"),
        ("CAGR (%/năm)", f"{vni_m['CAGR_%']:.2f}%", f"{v30_m['CAGR_%']:.2f}%", f"{b_m['CAGR_%']:.2f}%", f"{hrp_m['CAGR_%']:.2f}%", f"{mas_m['CAGR_%']:.2f}%"),
        ("Độ Lệch Chuẩn Năm (Vol %)", f"{vni_m['Ann_Vol_%']:.2f}%", f"{v30_m['Ann_Vol_%']:.2f}%", f"{b_m['Ann_Vol_%']:.2f}%", f"{hrp_m['Ann_Vol_%']:.2f}%", f"{mas_m['Ann_Vol_%']:.2f}%"),
        ("Max Drawdown (MDD %)", f"-{vni_m['MDD_%']:.2f}%", f"-{v30_m['MDD_%']:.2f}%", f"-{b_m['MDD_%']:.2f}%", f"-{hrp_m['MDD_%']:.2f}%", f"-{mas_m['MDD_%']:.2f}%"),
        ("Sharpe Ratio (Rf=0)", f"{vni_m['Sharpe_Zero']:.2f}", f"{v30_m['Sharpe_Zero']:.2f}", f"{b_m['Sharpe_Zero']:.2f}", f"{hrp_m['Sharpe_Zero']:.2f}", f"{mas_m['Sharpe_Zero']:.2f}"),
        ("Calmar Ratio", f"{vni_m['Calmar_Ratio']:.2f}", f"{v30_m['Calmar_Ratio']:.2f}", f"{b_m['Calmar_Ratio']:.2f}", f"{hrp_m['Calmar_Ratio']:.2f}", f"{mas_m['Calmar_Ratio']:.2f}"),
        ("Alpha vs VNINDEX (%/năm)", "-", "-", f"{b_m['Alpha_%']:+.2f}%", f"{hrp_m['Alpha_%']:+.2f}%", f"{mas_m['Alpha_%']:+.2f}%"),
        ("Beta vs VNINDEX", "1.00", f"{calc_relative_metrics(vn30_close, vnindex_close)['Beta']:.2f}", f"{b_m['Beta']:.2f}", f"{hrp_m['Beta']:.2f}", f"{mas_m['Beta']:.2f}"),
        ("Tương Quan vs VNINDEX (r)", "1.00", f"{calc_relative_metrics(vn30_close, vnindex_close)['Correlation']:.2f}", f"{b_m['Correlation']:.2f}", f"{hrp_m['Correlation']:.2f}", f"{mas_m['Correlation']:.2f}"),
        ("Khủng Hoảng 2022 (Return)", f"{vnindex_summaries['Regime_2_Bear_Market']['Total_Return_%']:+.2f}%", f"{vn30_summaries['Regime_2_Bear_Market']['Total_Return_%']:+.2f}%", f"{strat_summaries['1. Baseline (Quỹ + ADX)']['Regime_2_Bear_Market']['Total_Return_%']:+.2f}%", f"{strat_summaries['3. HRP Dynamic Sizing']['Regime_2_Bear_Market']['Total_Return_%']:+.2f}%", f"{strat_summaries['4. Master Combo (GARCH + HRP)']['Regime_2_Bear_Market']['Total_Return_%']:+.2f}%"),
        ("Khủng Hoảng 2022 (MDD)", f"-{vnindex_summaries['Regime_2_Bear_Market']['MDD_%']:.2f}%", f"-{vn30_summaries['Regime_2_Bear_Market']['MDD_%']:.2f}%", f"-{strat_summaries['1. Baseline (Quỹ + ADX)']['Regime_2_Bear_Market']['MDD_%']:.2f}%", f"-{strat_summaries['3. HRP Dynamic Sizing']['Regime_2_Bear_Market']['MDD_%']:.2f}%", f"-{strat_summaries['4. Master Combo (GARCH + HRP)']['Regime_2_Bear_Market']['MDD_%']:.2f}%"),
        ("Pha Choppy 2023-24 (Return)", f"{vnindex_summaries['Regime_3_Recovery']['Total_Return_%']:+.2f}%", f"{vn30_summaries['Regime_3_Recovery']['Total_Return_%']:+.2f}%", f"{strat_summaries['1. Baseline (Quỹ + ADX)']['Regime_3_Recovery']['Total_Return_%']:+.2f}%", f"{strat_summaries['3. HRP Dynamic Sizing']['Regime_3_Recovery']['Total_Return_%']:+.2f}%", f"{strat_summaries['4. Master Combo (GARCH + HRP)']['Regime_3_Recovery']['Total_Return_%']:+.2f}%"),
        ("Kỷ Nguyên Mới 2025-26 (Return)", f"{vnindex_summaries['Regime_4_New_Era']['Total_Return_%']:+.2f}%", f"{vn30_summaries['Regime_4_New_Era']['Total_Return_%']:+.2f}%", f"{strat_summaries['1. Baseline (Quỹ + ADX)']['Regime_4_New_Era']['Total_Return_%']:+.2f}%", f"{strat_summaries['3. HRP Dynamic Sizing']['Regime_4_New_Era']['Total_Return_%']:+.2f}%", f"{strat_summaries['4. Master Combo (GARCH + HRP)']['Regime_4_New_Era']['Total_Return_%']:+.2f}%")
    ]
    
    for r in rows:
        print(f"{r[0]:<30} | {r[1]:<10} | {r[2]:<10} | {r[3]:<10} | {r[4]:<10} | {r[5]:<10}")
    print("="*95)
    
    # Lưu JSON
    out_json = Path(r"C:\Users\X1 Yoga Gen 6\.gemini\antigravity\scratch\vn30_statistical_clustering\vnindex_comparison_summary.json")
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)
    print(f"Đã lưu kết quả định lượng chi tiết vào: {out_json}")
    
    # Vẽ biểu đồ đối chiếu 3 tầng chuyên nghiệp
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 14), sharex=True, gridspec_kw={'height_ratios': [2.5, 1.2, 1.0]})
    
    start_d = '2020-05-15'
    end_d = '2026-09-07'
    
    vni_sub = vnindex_close.loc[start_d:end_d]
    v30_sub = vn30_close.loc[start_d:end_d]
    
    vni_norm = vni_sub / vni_sub.iloc[0] * 100.0
    v30_norm = v30_sub / v30_sub.iloc[0] * 100.0
    
    ax1.plot(vni_norm.index, vni_norm, label=f"VN-INDEX (Lãi: {vni_m['Total_Return_%']:+.1f}%, MDD: -{vni_m['MDD_%']:.1f}%)", color='#e74c3c', linestyle=':', linewidth=2.2, alpha=0.9)
    ax1.plot(v30_norm.index, v30_norm, label=f"VN30 Index (Lãi: {v30_m['Total_Return_%']:+.1f}%, MDD: -{v30_m['MDD_%']:.1f}%)", color='#34495e', linestyle='--', linewidth=2.0, alpha=0.8)
    
    colors = {
        '1. Baseline (Quỹ + ADX)': ('#3498db', '-.', 1.8),
        '3. HRP Dynamic Sizing': ('#e67e22', '-', 2.6),
        '4. Master Combo (GARCH + HRP)': ('#27ae60', '-', 2.4)
    }
    
    for cname, (col, st, w) in colors.items():
        s_nav = strat_equities[cname].loc[start_d:end_d]
        s_norm = s_nav / s_nav.iloc[0] * 100.0
        ret_val = strat_summaries[cname]['Full_Period_2020_2026']['Total_Return_%']
        mdd_val = strat_summaries[cname]['Full_Period_2020_2026']['MDD_%']
        ax1.plot(s_norm.index, s_norm, label=f"{cname} (Lãi: {ret_val:+.1f}%, MDD: -{mdd_val:.1f}%)", color=col, linestyle=st, linewidth=w)
        
        dd_s = (s_nav - s_nav.cummax()) / s_nav.cummax() * 100.0
        ax2.plot(dd_s.index, dd_s, label=cname.split(' (')[0], color=col, linestyle=st, linewidth=1.5)
        
    vni_dd = (vni_sub - vni_sub.cummax()) / vni_sub.cummax() * 100.0
    v30_dd = (v30_sub - v30_sub.cummax()) / v30_sub.cummax() * 100.0
    ax2.plot(vni_dd.index, vni_dd, label="VN-INDEX", color='#e74c3c', linestyle=':', linewidth=2.0)
    ax2.plot(v30_dd.index, v30_dd, label="VN30", color='#34495e', linestyle='--', linewidth=1.5)
    
    # Panel 3: Rolling 60-day Beta & Correlation
    hrp_rets = strat_equities['3. HRP Dynamic Sizing'].loc[start_d:end_d].pct_change()
    vni_rets = vni_sub.pct_change()
    
    rolling_cov = hrp_rets.rolling(window=60).cov(vni_rets)
    rolling_var = vni_rets.rolling(window=60).var()
    rolling_beta = rolling_cov / rolling_var
    rolling_corr = hrp_rets.rolling(window=60).corr(vni_rets)
    
    ax3.plot(rolling_beta.index, rolling_beta, label="Rolling 60-Day Beta (HRP vs VN-Index)", color='#8e44ad', linewidth=1.8)
    ax3.plot(rolling_corr.index, rolling_corr, label="Rolling 60-Day Correlation (HRP vs VN-Index)", color='#16a085', linestyle='--', linewidth=1.5)
    ax3.axhline(0.0, color='gray', linestyle=':', alpha=0.7)
    ax3.axhline(0.5, color='gray', linestyle=':', alpha=0.5)
    ax3.set_ylabel("Beta / Correlation", fontsize=10, fontweight='bold')
    ax3.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9, fontsize=9)
    
    regime_dividers = [
        ('2022-01-01', 'Khủng Hoảng 2022 (Sập Hầm)'),
        ('2023-01-01', 'Phục Hồi 2023-2024 (Choppy)'),
        ('2025-01-01', 'Kỷ Nguyên Mới 2025-2026')
    ]
    for date_str, reg_name in regime_dividers:
        t_stamp = pd.Timestamp(date_str)
        for ax in [ax1, ax2, ax3]:
            ax.axvline(t_stamp, color='black', linestyle='--', linewidth=1.2, alpha=0.45)
        ax1.text(t_stamp + pd.Timedelta(days=5), 185, reg_name, fontsize=9, fontweight='bold', color='#2c3e50', alpha=0.85)
        
    ax1.set_title("ĐỐI CHIẾU HIỆU NĂNG TOÀN DIỆN VỚI THỊ TRƯỜNG CHUNG VN-INDEX & VN30 (2020 - 2026)", fontsize=13, fontweight='bold', pad=12)
    ax1.set_ylabel("Tăng Trưởng Chuẩn Hóa (Gốc = 100)", fontsize=11, fontweight='bold')
    ax1.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.92, fontsize=10)
    
    ax2.set_ylabel("Mức Sụt Giảm (%)", fontsize=11, fontweight='bold')
    ax2.legend(loc='lower left', frameon=True, facecolor='white', framealpha=0.92, fontsize=9)
    
    ax3.set_xlabel("Thời Gian Giao Dịch (2020 - 2026)", fontsize=11, fontweight='bold')
    
    plt.tight_layout()
    chart_p = Path(r"C:\Users\X1 Yoga Gen 6\.gemini\antigravity\brain\61ebd816-c2de-4f34-9687-0ea8fda25f31\vnindex_strategy_comparison.png")
    fig.savefig(chart_p, dpi=300)
    print(f"\nĐã xuất biểu đồ so sánh với VN-Index tại: {chart_p}")

if __name__ == '__main__':
    main()
