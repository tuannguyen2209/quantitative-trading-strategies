#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module: HRP & GJR-GARCH Econometric Engine
==========================================
Tích hợp:
1. Hierarchical Risk Parity (HRP) theo Marcos López de Prado
2. GJR-GARCH(1,1) Asymmetric Volatility & Tail Risk Early Warning
"""

import logging
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram

try:
    from arch import arch_model
    HAS_ARCH = True
except ImportError:
    HAS_ARCH = False

logger = logging.getLogger("HRP_GARCH")

class HierarchicalRiskParity:
    @staticmethod
    def get_cluster_var(cov: pd.DataFrame, c_items: List[str]) -> float:
        """
        Tính phương sai đại diện của cụm tài sản theo nghịch đảo phương sai (Inverse-Variance).
        """
        cov_slice = cov.loc[c_items, c_items].values
        diag = np.diag(cov_slice)
        w = 1.0 / np.clip(diag, 1e-8, None)
        w /= w.sum()
        val = float(w @ cov_slice @ w)
        return max(1e-8, val)

    @classmethod
    def compute_hrp_weights(cls, cov_mat: pd.DataFrame, linkage_z: np.ndarray) -> pd.Series:
        """
        Thực thi thuật toán HRP 3 bước:
        1. Quasi-Diagonalization qua Dendrogram Leaves
        2. Recursive Bisection (chia đôi đệ quy)
        3. Inverse-Cluster Variance Allocation
        """
        leaves = dendrogram(linkage_z, no_plot=True)['leaves']
        ordered_syms = [cov_mat.columns[i] for i in leaves]
        
        w = pd.Series(1.0, index=ordered_syms)
        c_items = [ordered_syms]
        
        while len(c_items) > 0:
            c_items = [i[j:k] for i in c_items for j, k in ((0, len(i) // 2), (len(i) // 2, len(i))) if len(i) > 1]
            for i in range(0, len(c_items), 2):
                c_items0 = c_items[i]
                c_items1 = c_items[i + 1]
                var0 = cls.get_cluster_var(cov_mat, c_items0)
                var1 = cls.get_cluster_var(cov_mat, c_items1)
                alpha = np.clip(1.0 - var0 / (var0 + var1), 0.05, 0.95)
                w[c_items0] *= alpha
                w[c_items1] *= (1.0 - alpha)
                
        w /= w.sum()
        return w

    @staticmethod
    def get_position_sizing(
        sym: str,
        hrp_weights: pd.Series,
        num_symbols: int,
        is_choppy: bool,
        is_uptrend: bool,
        is_tier2: bool
    ) -> float:
        """
        Chuyển đổi trọng số HRP thành tỷ trọng NAV thực chiến trong khoảng [15%, 35%]:
        - Cụm biến động thấp (trọng số HRP cao) -> tăng tỷ trọng
        - Cụm biến động giật cục / đầu cơ (trọng số HRP thấp) -> hạ tỷ trọng
        """
        avg_w = 1.0 / num_symbols
        sym_w = hrp_weights.get(sym, avg_w)
        rel_ratio = sym_w / avg_w # > 1.0 nếu rủi ro thấp, < 1.0 nếu rủi ro cao
        
        # Scale factor nén trong khoảng [0.70, 1.35]
        scale = np.clip(rel_ratio, 0.70, 1.35)
        
        if is_choppy:
            base_pct = 0.20
        else:
            if is_uptrend:
                base_pct = 0.35 if is_tier2 else 0.30
            else:
                base_pct = 0.20
                
        target_pct = base_pct * scale
        # Ràng buộc cứng an toàn vốn
        return float(np.clip(target_pct, 0.15, 0.35))

class GarchTailRiskManager:
    @staticmethod
    def evaluate_tail_risk(returns_slice: pd.Series) -> Tuple[bool, float, float]:
        """
        Dự báo rủi ro đuôi bất đối xứng bằng mô hình GJR-GARCH(1,1):
        sigma_t^2 = omega + (alpha + gamma * I_{eps < 0}) * eps_{t-1}^2 + beta * sigma_{t-1}^2
        
        Returns:
            (is_tail_risk, cond_vol_ann, vol_ratio)
        """
        # Nếu chuỗi quá ngắn hoặc không có arch
        if len(returns_slice) < 30 or not HAS_ARCH:
            # Fallback sang asymmetric downside EWMA
            down_rets = returns_slice[returns_slice < 0]
            down_std = down_rets.std() if len(down_rets) > 5 else returns_slice.std()
            hist_std = returns_slice.std()
            ratio = (down_std / hist_std) if hist_std > 0 else 1.0
            return (ratio > 1.30, float(down_std * np.sqrt(252)), float(ratio))
            
        try:
            # Quy đổi sang % để tối ưu hóa hội tụ số học
            scaled_rets = returns_slice * 100.0
            am = arch_model(scaled_rets, p=1, o=1, q=1, dist='Normal', rescale=False)
            res = am.fit(disp='off', show_warning=False)
            forecast = res.forecast(horizon=1)
            cond_vol_daily = np.sqrt(forecast.variance.iloc[-1].values[0]) / 100.0
            cond_vol_ann = cond_vol_daily * np.sqrt(252)
            
            # So sánh với biến động thực hiện 20 phiên
            hist_std = returns_slice.iloc[-20:].std()
            vol_ratio = (cond_vol_daily / hist_std) if hist_std > 0 else 1.0
            
            # Cảnh báo rủi ro đuôi nếu phương sai có điều kiện bùng nổ > 25%
            is_tail_risk = (vol_ratio >= 1.25)
            return (is_tail_risk, float(cond_vol_ann), float(vol_ratio))
        except Exception:
            # Fallback nếu GARCH không hội tụ
            hist_std = returns_slice.iloc[-20:].std()
            full_std = returns_slice.std()
            ratio = (hist_std / full_std) if full_std > 0 else 1.0
            return (ratio > 1.30, float(hist_std * np.sqrt(252)), float(ratio))
