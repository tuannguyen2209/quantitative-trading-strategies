#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module: VN30 Statistical Clustering Universe (Sector Rotation T+5)
==================================================================
Mục tiêu:
Gom 30 cổ phiếu thuộc rổ VN30 thành các cụm thống kê (Statistical Clusters)
dựa trên mức độ đồng pha giá và dòng tiền thực tế thay vì phân ngành ICB định tính.
Giúp tránh rủi ro tập trung (concentration risk) và nhận diện các mã luân chuyển dòng tiền T+5/T+6.

Tác giả: Antigravity Quant Team
Phiên bản: 1.0.0
"""

import os
import json
import logging
import argparse
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.spatial.distance import squareform
from scipy.cluster.hierarchy import linkage, fcluster, dendrogram
from sklearn.metrics import silhouette_score

# Cấu hình logging chuyên nghiệp
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('VN30Clustering')

# Danh sách 30 mã VN30 mặc định làm fallback an toàn
DEFAULT_VN30_TICKERS = [
    'ACB', 'BID', 'BSR', 'CTG', 'FPT', 'GAS', 'GVR', 'HDB', 'HPG', 'LPB',
    'MBB', 'MCH', 'MSN', 'MWG', 'SAB', 'SHB', 'SSB', 'SSI', 'STB', 'TCB',
    'TCX', 'VCB', 'VHM', 'VIB', 'VIC', 'VJC', 'VNM', 'VPB', 'VPL', 'VRE'
]


# ==============================================================================
# BƯỚC 1: DATA INGESTION & RETURNS MATRIX
# ==============================================================================

def get_vn30_symbols() -> List[str]:
    """
    Lấy danh sách các mã cổ phiếu hiện tại trong rổ VN30.
    Ưu tiên lấy động qua vnstock Listing, có fallback an toàn.
    """
    try:
        from vnstock import Listing
        listing = Listing()
        symbols = listing.symbols_by_group('VN30')
        if symbols is not None and len(symbols) > 0:
            sym_list = symbols.tolist() if hasattr(symbols, 'tolist') else list(symbols)
            logger.info(f'Đã tải thành công danh sách VN30 ({len(sym_list)} mã) từ vnstock.')
            return sym_list
    except Exception as exc:
        logger.warning(f'Không thể lấy động danh mục VN30 ({exc}). Sử dụng danh sách cấu hình mặc định.')
    
    return DEFAULT_VN30_TICKERS.copy()


def _fetch_single_symbol(symbol: str, lookback_days: int = 250) -> Tuple[str, Optional[pd.DataFrame]]:
    """
    Tải dữ liệu OHLCV cho một mã riêng biệt từ vnstock với cơ chế fallback nguồn dữ liệu.
    """
    from vnstock import Quote
    from datetime import datetime, timedelta

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

    for source in ['kbs', 'vci', 'msn']:
        try:
            q = Quote(symbol=symbol, source=source)
            df = q.history(start=start_date, end=end_date)
            if df is not None and not df.empty and 'close' in df.columns and 'volume' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                df = df.sort_values('time').drop_duplicates(subset=['time'])
                return symbol, df[['time', 'close', 'volume']].reset_index(drop=True)
        except Exception:
            continue

    logger.warning(f'Không thể lấy dữ liệu online cho mã: {symbol}')
    return symbol, None


def fetch_vn30_data(
    lookback_sessions: int = 90,
    cache_dir: str = '.cache',
    use_cache: bool = True
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    Tải chuỗi dữ liệu giá đóng cửa (close) và khối lượng (volume) của 30 mã VN30 và chỉ số VN30.
    
    Parameters:
    -----------
    lookback_sessions : int
        Số phiên giao dịch quan sát (mặc định 90 phiên).
    cache_dir : str
        Thư mục lưu cache cục bộ để tăng tốc độ xử lý.
    use_cache : bool
        Có đọc từ file cache cục bộ nếu khả dụng hay không.
        
    Returns:
    --------
    Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]:
        - price_df: Ma trận giá đóng cửa [T x 30]
        - volume_df: Ma trận khối lượng [T x 30]
        - vn30_price: Chuỗi giá đóng cửa của chỉ số VN30 [T]
        - returns_df: Ma trận log returns R [T x 30]
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_file = cache_path / f'vn30_data_cache_{lookback_sessions}.parquet'

    data_loaded = False
    price_df = pd.DataFrame()
    volume_df = pd.DataFrame()
    vn30_price = pd.Series(dtype=float)

    # 1. Kiểm tra cache
    if use_cache and cache_file.exists():
        try:
            full_df = pd.read_parquet(cache_file)
            price_cols = [c for c in full_df.columns if c.startswith('close_')]
            volume_cols = [c for c in full_df.columns if c.startswith('volume_')]
            
            price_df = full_df[price_cols].rename(columns=lambda c: c.replace('close_', ''))
            volume_df = full_df[volume_cols].rename(columns=lambda c: c.replace('volume_', ''))
            if 'VN30_close' in full_df.columns:
                vn30_price = full_df['VN30_close']
                vn30_price.index = full_df.index
            
            logger.info(f'Đã tải thành công {len(price_df)} phiên từ file cache: {cache_file}')
            data_loaded = True
        except Exception as e:
            logger.warning(f'Lỗi đọc cache: {e}. Tiến hành tải mới dữ liệu từ API.')

    # 2. Nếu chưa có cache, tải dữ liệu từ vnstock
    if not data_loaded:
        symbols = get_vn30_symbols()
        all_targets = symbols + ['VN30']
        logger.info(f'Bắt đầu thu thập dữ liệu song song cho {len(all_targets)} mã (gồm cả chỉ số VN30)...')

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            future_to_symbol = {
                executor.submit(_fetch_single_symbol, sym, lookback_days=int(lookback_sessions * 2.5)): sym
                for sym in all_targets
            }
            for future in concurrent.futures.as_completed(future_to_symbol):
                sym = future_to_symbol[future]
                try:
                    s_name, df = future.result()
                    if df is not None and not df.empty:
                        results[s_name] = df
                except Exception as exc:
                    logger.error(f'Lỗi khi tải mã {sym}: {exc}')

        if 'VN30' in results:
            vn30_raw = results.pop('VN30').set_index('time')['close']
        else:
            logger.warning('Không có dữ liệu chỉ số VN30 riêng, tính toán VN30 từ giá trị bình quân rổ.')
            vn30_raw = None

        temp_prices = {}
        temp_volumes = {}
        for sym, df in results.items():
            df = df.set_index('time')
            temp_prices[sym] = df['close']
            temp_volumes[sym] = df['volume']

        raw_price_df = pd.DataFrame(temp_prices)
        raw_volume_df = pd.DataFrame(temp_volumes)

        # Xử lý missing values: forward-fill và bfill
        raw_price_df = raw_price_df.ffill().bfill()
        raw_volume_df = raw_volume_df.ffill().fillna(0)

        # Đồng bộ index với VN30
        if vn30_raw is not None:
            common_idx = raw_price_df.index.intersection(vn30_raw.index)
            raw_price_df = raw_price_df.loc[common_idx]
            raw_volume_df = raw_volume_df.loc[common_idx]
            vn30_price = vn30_raw.loc[common_idx]
        else:
            vn30_price = raw_price_df.mean(axis=1)

        # Lấy đúng T + 1 phiên giá để có đúng T = lookback_sessions phiên log returns
        needed_sessions = lookback_sessions + 1
        if len(raw_price_df) > needed_sessions:
            price_df = raw_price_df.iloc[-needed_sessions:]
            volume_df = raw_volume_df.iloc[-needed_sessions:]
            vn30_price = vn30_price.iloc[-needed_sessions:]
        else:
            price_df = raw_price_df
            volume_df = raw_volume_df
            vn30_price = vn30_price

        # Lưu cache parquet
        try:
            save_df = pd.DataFrame(index=price_df.index)
            for c in price_df.columns:
                save_df[f'close_{c}'] = price_df[c]
                save_df[f'volume_{c}'] = volume_df[c]
            save_df['VN30_close'] = vn30_price
            save_df.to_parquet(cache_file)
            logger.info(f'Đã lưu cache dữ liệu tại: {cache_file}')
        except Exception as e:
            logger.warning(f'Không thể lưu cache: {e}')

    # 3. Tính toán ma trận Log Returns R = ln(P_t / P_{t-1})
    log_returns = np.log(price_df / price_df.shift(1)).dropna()
    if len(log_returns) > lookback_sessions:
        log_returns = log_returns.iloc[-lookback_sessions:]

    logger.info(f'Ma trận lợi suất Log Returns kích thước: {log_returns.shape} (Phiên x Cổ phiếu)')
    return price_df, volume_df, vn30_price, log_returns


# ==============================================================================
# BƯỚC 2: DISTANCE METRIC TRANSFORMATION
# ==============================================================================

def compute_correlation_distance(
    returns_df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """
    Tính ma trận hệ số tương quan Pearson C và chuyển đổi sang ma trận khoảng cách metric Euclidean:
    D_{i, j} = sqrt(2 * (1 - rho_{ij}))
    """
    corr_df = returns_df.corr(method='pearson')
    rho_values = corr_df.values
    distance_values = np.sqrt(np.clip(2.0 * (1.0 - rho_values), 0.0, 4.0))
    np.fill_diagonal(distance_values, 0.0)
    
    dist_df = pd.DataFrame(distance_values, index=corr_df.index, columns=corr_df.columns)
    condensed_dist = squareform(distance_values, checks=True)
    
    logger.info(f'Khoảng cách Euclidean min={distance_values.min():.4f}, max={distance_values.max():.4f}')
    return corr_df, dist_df, condensed_dist


# ==============================================================================
# BƯỚC 3: HIERARCHICAL ASCENDING CLUSTERING (HAC)
# ==============================================================================

def perform_clustering(
    dist_df: pd.DataFrame,
    condensed_dist: np.ndarray,
    k_range: Tuple[int, int] = (4, 6)
) -> Tuple[pd.Series, int, Dict[int, float], np.ndarray]:
    """
    Áp dụng thuật toán gom cụm phân cấp thứ bậc (HAC) với Ward Linkage.
    Tự động chọn số cụm tối ưu K dựa trên Silhouette Score lớn nhất.
    """
    linkage_matrix = linkage(condensed_dist, method='ward')
    
    silhouette_dict = {}
    best_score = -2.0
    optimal_k = k_range[0]
    
    symbols = dist_df.index.tolist()
    dist_matrix = dist_df.values
    
    for k in range(k_range[0], k_range[1] + 1):
        labels = fcluster(linkage_matrix, t=k, criterion='maxclust')
        score = silhouette_score(dist_matrix, labels, metric='precomputed')
        silhouette_dict[k] = float(score)
        logger.info(f'K = {k} -> Silhouette Score = {score:.4f}')
        
        if score > best_score:
            best_score = score
            optimal_k = k
            
    logger.info(f'=> Số cụm tối ưu được chọn: K* = {optimal_k} với Silhouette Score = {best_score:.4f}')
    
    optimal_labels = fcluster(linkage_matrix, t=optimal_k, criterion='maxclust')
    cluster_labels = pd.Series(optimal_labels, index=symbols, name='Cluster_ID')
    
    return cluster_labels, optimal_k, silhouette_dict, linkage_matrix


# ==============================================================================
# BƯỚC 4: CLUSTER SYNTHESIS & METRICS CALCULATION
# ==============================================================================

def evaluate_clusters(
    price_df: pd.DataFrame,
    volume_df: pd.DataFrame,
    vn30_price: pd.Series,
    cluster_labels: pd.Series
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Tính các chỉ số tổng hợp định lượng cho từng cụm:
    1. Cluster Synthetic Price Index: Chỉ số giá trung bình có trọng số thanh khoản (Volume-Weighted)
    2. Relative Volume (RVOL): Tổng volume phiên gần nhất so với SMA(20) của cụm
    3. Cluster Relative Strength (RS): Tỷ số giữa Synthetic Index so với chỉ số VN30
    4. RS Momentum (5 phiên): Động lượng sức mạnh giá chu kỳ T+5
    """
    unique_clusters = sorted(cluster_labels.unique())
    norm_prices = 100.0 * (price_df / price_df.iloc[0])
    norm_vn30 = 100.0 * (vn30_price / vn30_price.iloc[0])
    
    synthetic_indices = {}
    metrics_records = []
    
    for cluster_id in unique_clusters:
        stocks_in_cluster = cluster_labels[cluster_labels == cluster_id].index.tolist()
        sub_prices = norm_prices[stocks_in_cluster]
        sub_volumes = volume_df[stocks_in_cluster]
        
        total_cluster_volume = sub_volumes.sum(axis=1)
        safe_total_volume = total_cluster_volume.replace(0, np.nan)
        weights = sub_volumes.div(safe_total_volume, axis=0).fillna(1.0 / len(stocks_in_cluster))
        
        synthetic_index = (weights * sub_prices).sum(axis=1)
        synthetic_indices[f'Cluster_{cluster_id}'] = synthetic_index
        
        sma20_volume = total_cluster_volume.rolling(window=20, min_periods=5).mean()
        rvol = float(total_cluster_volume.iloc[-1] / sma20_volume.iloc[-1]) if sma20_volume.iloc[-1] > 0 else 1.0
        
        cluster_rs_series = synthetic_index / norm_vn30
        latest_rs = float(cluster_rs_series.iloc[-1])
        
        if len(cluster_rs_series) >= 6:
            rs_mom_5d = float((cluster_rs_series.iloc[-1] / cluster_rs_series.iloc[-6]) - 1.0)
        else:
            rs_mom_5d = float((cluster_rs_series.iloc[-1] / cluster_rs_series.iloc[0]) - 1.0)
            
        metrics_records.append({
            'Cluster_ID': int(cluster_id),
            'Member_Count': len(stocks_in_cluster),
            'Members': ', '.join(stocks_in_cluster),
            'RVOL': round(rvol, 3),
            'Cluster_RS': round(latest_rs, 4),
            'RS_Momentum_5D_%': round(rs_mom_5d * 100.0, 2)
        })
        
    cluster_metrics_df = pd.DataFrame(metrics_records).set_index('Cluster_ID')
    synthetic_indices_df = pd.DataFrame(synthetic_indices, index=price_df.index)
    
    return cluster_metrics_df, synthetic_indices_df


def get_top_momentum_per_cluster(
    price_df: pd.DataFrame,
    vn30_price: pd.Series,
    cluster_labels: pd.Series,
    momentum_window: int = 5
) -> pd.DataFrame:
    """
    Xác định 1 mã cổ phiếu có Relative Strength / Momentum T+5 mạnh nhất đại diện cho mỗi cụm.
    """
    norm_stock_prices = price_df.div(price_df.iloc[0], axis=1)
    norm_vn30 = vn30_price / vn30_price.iloc[0]
    stock_rs = norm_stock_prices.div(norm_vn30, axis=0)
    
    rs_momentum = (stock_rs.iloc[-1] / stock_rs.iloc[-1 - momentum_window] - 1.0) * 100.0
    price_returns_5d = (price_df.iloc[-1] / price_df.iloc[-1 - momentum_window] - 1.0) * 100.0
    
    top_picks = []
    for cluster_id in sorted(cluster_labels.unique()):
        stocks = cluster_labels[cluster_labels == cluster_id].index
        sub_rs_mom = rs_momentum.loc[stocks]
        
        top_stock = sub_rs_mom.idxmax()
        top_picks.append({
            'Cluster_ID': int(cluster_id),
            'Top_Stock': str(top_stock),
            'RS_Momentum_5D_%': round(float(sub_rs_mom.loc[top_stock]), 2),
            'Price_Return_5D_%': round(float(price_returns_5d.loc[top_stock]), 2),
            'Cluster_Members': list(stocks)
        })
        
    return pd.DataFrame(top_picks).set_index('Cluster_ID')


# ==============================================================================
# BƯỚC 5: VISUALIZATION & EXPORT
# ==============================================================================

def plot_clustering_visualizations(
    linkage_matrix: np.ndarray,
    corr_df: pd.DataFrame,
    cluster_labels: pd.Series,
    optimal_k: int,
    output_dir: Path
) -> Tuple[Path, Path]:
    """
    Vẽ 2 biểu đồ trực quan hóa chuyên sâu:
    1. Dendrogram thể hiện cấu trúc cây phân cấp thứ bậc và đường cắt ngưỡng.
    2. Clustered Correlation Heatmap sắp xếp lại theo cụm đồng pha giá.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    # 1. DENDROGRAM
    fig, ax = plt.subplots(figsize=(14, 7), dpi=300)
    dendro_threshold = (linkage_matrix[-(optimal_k - 1), 2] + linkage_matrix[-optimal_k, 2]) / 2.0
    
    dendro = dendrogram(
        linkage_matrix,
        labels=corr_df.index.tolist(),
        color_threshold=dendro_threshold,
        above_threshold_color='#7f8c8d',
        leaf_rotation=90,
        leaf_font_size=10.5,
        ax=ax
    )
    
    ax.axhline(
        y=dendro_threshold,
        color='#e74c3c',
        linestyle='--',
        linewidth=1.8,
        label=f'Cut-off Threshold = {dendro_threshold:.3f} (K={optimal_k})'
    )
    
    ax.set_title(
        f'VN30 Hierarchical Ascending Clustering (HAC - Ward Linkage)\nLookback 90 Phien - So Cum Toi Uu K* = {optimal_k}',
        fontsize=13, fontweight='bold', pad=15
    )
    ax.set_xlabel('Ma Co Phieu Ro VN30', fontsize=11, labelpad=10)
    ax.set_ylabel('Khoang Cach Metric D = sqrt(2(1 - rho))', fontsize=11, labelpad=10)
    ax.legend(loc='upper right', frameon=True, fontsize=10.5)
    fig.tight_layout()
    
    dendro_path = output_dir / 'vn30_dendrogram.png'
    fig.savefig(dendro_path, dpi=300)
    plt.close(fig)
    logger.info(f'Da luu bieu do Dendrogram tai: {dendro_path}')
    
    # 2. CLUSTERED CORRELATION HEATMAP
    sorted_stocks = cluster_labels.sort_values().index.tolist()
    reordered_corr = corr_df.loc[sorted_stocks, sorted_stocks]
    
    fig, ax = plt.subplots(figsize=(13, 11), dpi=300)
    cmap = sns.diverging_palette(240, 10, s=80, l=55, as_cmap=True)
    
    sns.heatmap(
        reordered_corr,
        cmap=cmap,
        vmin=-0.2,
        vmax=1.0,
        annot=True,
        fmt='.2f',
        annot_kws={'size': 7.5, 'weight': 'normal'},
        linewidths=0.5,
        linecolor='#ffffff',
        cbar_kws={'label': 'He So Tuong Quan Pearson (rho)', 'shrink': 0.8},
        ax=ax
    )
    
    cum_count = 0
    for cluster_id in sorted(cluster_labels.unique()):
        count = (cluster_labels == cluster_id).sum()
        ax.add_patch(plt.Rectangle(
            (cum_count, cum_count),
            count, count,
            fill=False,
            edgecolor='#2c3e50',
            lw=2.5
        ))
        ax.text(
            cum_count + count / 2.0,
            -0.5,
            f'Cluster {cluster_id}',
            ha='center', va='bottom',
            fontsize=10, fontweight='bold',
            color='#2c3e50'
        )
        cum_count += count
        
    ax.set_title(
        'VN30 Clustered Correlation Heatmap (Dong Pha Gia & Dong Tien)\nTai sap xep theo cau truc cum thong ke HAC',
        fontsize=13, fontweight='bold', pad=25
    )
    fig.tight_layout()
    
    heatmap_path = output_dir / 'vn30_clustered_heatmap.png'
    fig.savefig(heatmap_path, dpi=300)
    plt.close(fig)
    logger.info(f'Da luu bieu do Clustered Heatmap tai: {heatmap_path}')
    
    return dendro_path, heatmap_path


def export_results_to_json(
    cluster_metrics_df: pd.DataFrame,
    top_picks_df: pd.DataFrame,
    output_path: Path
) -> None:
    """
    Xuất kết quả phân cụm và các chỉ số định lượng ra file JSON có cấu trúc.
    """
    output_dict = {}
    
    for cluster_id in cluster_metrics_df.index:
        members = [s.strip() for s in str(cluster_metrics_df.loc[cluster_id, 'Members']).split(',')]
        rvol = float(cluster_metrics_df.loc[cluster_id, 'RVOL'])
        rs = float(cluster_metrics_df.loc[cluster_id, 'Cluster_RS'])
        rs_mom = float(cluster_metrics_df.loc[cluster_id, 'RS_Momentum_5D_%'])
        top_stock = str(top_picks_df.loc[cluster_id, 'Top_Stock'])
        top_mom = float(top_picks_df.loc[cluster_id, 'RS_Momentum_5D_%'])
        
        output_dict[f'Cluster_{cluster_id}'] = {
            'stocks': members,
            'member_count': len(members),
            'rvol': rvol,
            'rs': rs,
            'rs_momentum_5d_pct': rs_mom,
            'top_momentum_stock': top_stock,
            'top_stock_rs_momentum_5d_pct': top_mom
        }
        
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_dict, f, indent=2, ensure_ascii=False)
        
    logger.info(f'Da xuat ket qua thanh cong ra file JSON: {output_path}')


# ==============================================================================
# PIPELINE ORCHESTRATOR CLASS
# ==============================================================================

class VN30ClusteringUniverse:
    """
    Class điều phối toàn diện cho Module Statistical Clustering Universe VN30.
    """
    def __init__(self, lookback_sessions: int = 90, cache_dir: str = '.cache'):
        self.lookback = lookback_sessions
        self.cache_dir = cache_dir
        self.price_df: Optional[pd.DataFrame] = None
        self.volume_df: Optional[pd.DataFrame] = None
        self.vn30_price: Optional[pd.Series] = None
        self.returns_df: Optional[pd.DataFrame] = None
        self.corr_df: Optional[pd.DataFrame] = None
        self.dist_df: Optional[pd.DataFrame] = None
        self.condensed_dist: Optional[np.ndarray] = None
        self.cluster_labels: Optional[pd.Series] = None
        self.optimal_k: int = 0
        self.silhouette_dict: Dict[int, float] = {}
        self.linkage_matrix: Optional[np.ndarray] = None
        self.cluster_metrics_df: Optional[pd.DataFrame] = None
        self.synthetic_indices_df: Optional[pd.DataFrame] = None
        self.top_picks_df: Optional[pd.DataFrame] = None

    def run(self, k_range: Tuple[int, int] = (4, 6), output_dir: str = '.') -> Dict:
        """
        Thực thi trọn vẹn toàn bộ 5 bước của quy trình phân cụm thống kê.
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        logger.info('=== BUOC 1: LAY DU LIEU VA TINH MA TRAN LOI SUAT ===')
        self.price_df, self.volume_df, self.vn30_price, self.returns_df = fetch_vn30_data(
            lookback_sessions=self.lookback,
            cache_dir=self.cache_dir
        )
        
        logger.info('=== BUOC 2: TINH TOAN MA TRAN KHOANG CACH EUCLIDEAN TU CORRELATION ===')
        self.corr_df, self.dist_df, self.condensed_dist = compute_correlation_distance(self.returns_df)
        
        logger.info('=== BUOC 3: PHAN CUM PHAN CAP THU BAC (HAC) & TOI UU K ===')
        self.cluster_labels, self.optimal_k, self.silhouette_dict, self.linkage_matrix = perform_clustering(
            self.dist_df, self.condensed_dist, k_range=k_range
        )
        
        logger.info('=== BUOC 4: TONG HOP CUM & TINH TOAN METRICS (SYNTHETIC INDEX, RVOL, RS) ===')
        self.cluster_metrics_df, self.synthetic_indices_df = evaluate_clusters(
            self.price_df, self.volume_df, self.vn30_price, self.cluster_labels
        )
        self.top_picks_df = get_top_momentum_per_cluster(
            self.price_df, self.vn30_price, self.cluster_labels, momentum_window=5
        )
        
        logger.info('=== BUOC 5: TRUC QUAN HOA & XUAT KET QUA ===')
        dendro_file, heatmap_file = plot_clustering_visualizations(
            self.linkage_matrix, self.corr_df, self.cluster_labels, self.optimal_k, out_path
        )
        
        json_file = out_path / 'vn30_statistical_clusters.json'
        export_results_to_json(self.cluster_metrics_df, self.top_picks_df, json_file)
        
        return {
            'optimal_k': self.optimal_k,
            'silhouette_scores': self.silhouette_dict,
            'cluster_metrics': self.cluster_metrics_df,
            'top_picks': self.top_picks_df,
            'dendrogram_path': str(dendro_file),
            'heatmap_path': str(heatmap_file),
            'json_path': str(json_file)
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='VN30 Statistical Clustering Universe Selection')
    parser.add_argument('--lookback', type=int, default=90, help='So phien quan sat (default: 90)')
    parser.add_argument('--min-k', type=int, default=4, help='So cum toi thieu (default: 4)')
    parser.add_argument('--max-k', type=int, default=6, help='So cum toi da (default: 6)')
    parser.add_argument('--output-dir', type=str, default='.', help='Thu muc xuat ket qua')
    parser.add_argument('--cache-dir', type=str, default='.cache', help='Thu muc luu cache du lieu')
    
    args = parser.parse_args()
    
    orchestrator = VN30ClusteringUniverse(
        lookback_sessions=args.lookback,
        cache_dir=args.cache_dir
    )
    results = orchestrator.run(k_range=(args.min_k, args.max_k), output_dir=args.output_dir)
    
    print('\n' + '=' * 75)
    print('BANG TONG HOP CAC CUM THONG KE VN30 (SECTOR ROTATION T+5)')
    print('=' * 75)
    print(results['cluster_metrics'][['Member_Count', 'RVOL', 'Cluster_RS', 'RS_Momentum_5D_%', 'Members']])
    print('\n' + '=' * 75)
    print('TOP 1 MA CO PHIEU MOMENTUM DAI DIEN MOI CUM (T+5 SELECTION)')
    print('=' * 75)
    print(results['top_picks'][['Top_Stock', 'RS_Momentum_5D_%', 'Price_Return_5D_%']])
    print('=' * 75)
