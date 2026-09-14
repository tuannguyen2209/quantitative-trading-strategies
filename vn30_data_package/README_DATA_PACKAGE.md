# BỘ DỮ LIỆU ĐỊNH LƯỢNG CHIẾN LƯỢC VN30 QUANTITATIVE TRADING (2020 - 2026)

Thư mục này chứa toàn bộ dữ liệu lịch sử chuẩn hóa, kết quả mô hình phân cụm thống kê, trọng số Hierarchical Risk Parity (HRP), nhật ký giao dịch và phiếu lệnh thực chiến.

**Thời gian dữ liệu:** 02/01/2020 – 11/09/2026 (1668 phiên giao dịch).

---

## CẤU TRÚC THƯ MỤC

### 📁 `1_market_indices/` (Dữ Liệu Chỉ Số Thị Trường & Ma Trận Giá)
- **`VNINDEX_2020_2026.csv`**: Dữ liệu OHLCV lịch sử chỉ số VN-INDEX.
- **`VN30_Index_2020_2026.csv`**: Dữ liệu OHLCV lịch sử chỉ số VN30 Index.
- **`VN30F1M_2020_2026.csv`**: Dữ liệu OHLCV lịch sử hợp đồng tương lai phái sinh VN30F1M.
- **`VN30_All_Stocks_Close_Prices.csv`**: Ma trận giá đóng cửa (Close) của toàn bộ 30 cổ phiếu rổ VN30 qua từng phiên.
- **`VN30_All_Stocks_Volumes.csv`**: Ma trận khối lượng khớp lệnh (Volume) của 30 cổ phiếu rổ VN30.

### 📁 `2_individual_stocks_vn30/` (Dữ Liệu Từng Cổ Phiếu Riêng Lẻ)
Bao gồm 30 file CSV chuẩn OHLCV cho từng mã cổ phiếu rổ VN30:
`ACB_2020_2026.csv`, `BID_2020_2026.csv`, `CTG_2020_2026.csv`, `FPT_2020_2026.csv`, `HPG_2020_2026.csv`, `MBB_2020_2026.csv`, `MSN_2020_2026.csv`, `MWG_2020_2026.csv`, `SSI_2020_2026.csv`, `STB_2020_2026.csv`, `TCB_2020_2026.csv`, `VCB_2020_2026.csv`, `VHM_2020_2026.csv`, `VIC_2020_2026.csv`, `VNM_2020_2026.csv`, `VPB_2020_2026.csv`, `VRE_2020_2026.csv`, v.v.
*Định dạng:* `Date, Open, High, Low, Close, Volume` (Thích hợp import vào Excel, Pandas, AmiBroker, TradingView).

### 📁 `3_clustering_and_hrp_models/` (Mô Hình Phân Cụm & Phân Bổ Vốn HRP)
- **`vn30_statistical_clusters.json`**: Cấu trúc các cụm ngành thống kê thu được từ thuật toán phân cấp Ward HAC.
- **`hrp_weights_latest.json`**: Trọng số phân bổ vốn tối ưu HRP (Hierarchical Risk Parity của Marcos López de Prado) tính trên cửa sổ 90 phiên gần nhất.

### 📁 `4_performance_and_trade_logs/` (Báo Cáo Hiệu Suất & Nhật Ký Giao Dịch)
- **`vn30_hrp_full_trades_log_2020_2026.csv`**: Nhật ký toàn bộ các lệnh giao dịch thực tế qua 6.5 năm (ngày vào, ngày ra, giá mua, giá bán, lãi/lỗ %, lý do thoát lệnh).
- **`vn30_hrp_daily_nav_equity_curve_2020_2026.csv`**: Đường cong tăng trưởng tài sản ròng NAV theo từng ngày.
- **`vn30_hrp_garch_summary.json`**: Thống kê định lượng 4 kịch bản nâng cấp (Baseline vs GARCH vs HRP vs Combo).
- **`vnindex_comparison_summary.json`**: Báo cáo đối chiếu chi tiết các chỉ số Alpha, Beta, Sharpe, Calmar, MDD so với VN-Index.
- **`fmarket_equity_funds.json`**: Số liệu đối chiếu trực tiếp với 68 quỹ mở cổ phiếu trên Fmarket.

### 📁 `5_live_execution/` (Công Cụ Thực Thi Lệnh Hàng Ngày)
- **`daily_order_sheet.csv`**: Phiếu lệnh thực thi hôm nay (khối lượng, thị giá, trần thanh khoản 5% ADV20, phương thức đặt lệnh TWAP/ATC).
- **`portfolio_state.json`**: Trạng thái danh mục hiện tại (các vị thế đang nắm giữ, giá vốn, ngày nắm giữ, tỷ lệ lãi/lỗ).
