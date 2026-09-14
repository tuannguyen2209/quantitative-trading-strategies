# VN30 Quantitative Trading System (2020 - 2026)
### *Thuật toán Phân cụm Thống kê Ward HAC & Phân bổ Vốn Động Hierarchical Risk Parity (HRP)*

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Sharpe Ratio](https://img.shields.io/badge/Sharpe%20Ratio-1.04-success.svg)](#)
[![Max Drawdown](https://img.shields.io/badge/Max%20Drawdown--12.61%25-brightgreen.svg)](#)
[![Alpha vs VN-Index](https://img.shields.io/badge/Alpha%20vs%20VNINDEX-%2B7.06%25%2Fyr-orange.svg)](#)

Hệ thống giao dịch định lượng chuẩn mực dành cho rổ **30 cổ phiếu hàng đầu thị trường chứng khoán Việt Nam (VN30)** và hợp đồng tương lai chỉ số **VN30F1M**, tối ưu hóa cho quy mô vốn từ **5 tỷ đến 50 tỷ VNĐ**.

---

## 📊 BẢNG TỔNG KẾT HIỆU NĂNG TOÀN CHU KỲ (2020 - 2026)

Kiểm định Walk-Forward xuyên suốt **1,664 phiên giao dịch** (từ 15/05/2020 đến 11/09/2026), sau khi trừ đầy đủ phí giao dịch, thuế, trượt giá phi tuyến Almgren-Chriss và khống chế trần 5% ADV20:

| Chỉ Số Định Lượng | 👑 Hệ Thống HRP (Chiến Lược) | VN-INDEX (Thị Trường) | VN30 INDEX | DCDS (Dragon Capital) | VESAF (VinaCapital) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Tổng Lợi Nhuận Tích Lũy** | **+80.71%** | +120.26% | +151.43% | +34.34% *(5Y)* | +32.62% *(5Y)* |
| **CAGR (Tăng Trưởng Năm)** | **9.93%/năm** | 13.47%/năm | 15.90%/năm | ~9.0%/năm | ~8.5%/năm |
| **Độ Biến Động Năm ($\sigma_{Ann}$)** | **9.58% (RẤT MƯỢT)** | 19.37% | 20.54% | 21.5% | 18.2% |
| **MAX DRAWDOWN (MDD)** | **-12.61% (NÉN 70% RỦI RO)**| **-40.34% (SẬP HẦM)** | **-42.46% (CHÁY TK)**| **-38.2%** | **-28.5%** |
| **SHARPE RATIO ($R_f=0$)** | **1.04 (VƯỢT MỐC 1.0)** | 0.75 | 0.82 | 0.65 | 0.85 |
| **CALMAR RATIO (CAGR / MDD)** | **0.79 (VÔ ĐỊCH)** | 0.33 | 0.37 | 0.37 | 0.61 |
| **ALPHA vs VN-INDEX** | **+7.06%/năm** | - | - | - | - |
| **BETA vs VN-INDEX** | **0.20 (ASYMMETRIC LOW-BETA)** | 1.00 | 1.01 | ~0.90 | ~0.85 |
| **Khủng Hoảng 2022** | **-5.58% (BẢO TOÀN VỐN GỐC)**| **-33.99% (Sập Đổ)** | **-35.52%** | **-34.4%** | **-24.4%** |
| **Kỷ Nguyên Mới (2025 - 2026)** | **+52.04% (BÙNG NỔ)** | +43.47% | +46.14% | +32.9% | +6.3% |

---

## 🧠 KIẾN TRÚC TOÁN HỌC & ĐỊNH LƯỢNG 5 TẦNG

```
                    ┌─────────────────────────────────────────┐
                    │      VĨ MÔ & VI CẤU TRÚC THỊ TRƯỜNG     │
                    │  (VN30 ADX14 Filter + Phái Sinh Basis)  │
                    └────────────────────┬────────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │     PHÂN CỤM THỐNG KÊ (WARD HAC)        │
                    │    Ma Trận Tương Quan Sinh Dendrogram   │
                    └────────────────────┬────────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │      PHÂN BỔ VỐN ĐỘNG HRP (DE PRADO)    │
                    │  Inverse-Variance + Recursive Bisection │
                    └────────────────────┬────────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │       BỘ LỌC TÍN HIỆU XUNG LỰC VSA      │
                    │      RVOL >= 1.6 + Breakout Đỉnh 3D     │
                    └────────────────────┬────────────────────┘
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │   QUẢN TRỊ RỦI RO & CHỐT LỜI ĐỘNG       │
                    │   GJR-GARCH Tail Defense + Time-Stop    │
                    └─────────────────────────────────────────┘
```

1. **Phân Cụm Thống Kê (Ward Hierarchical Agglomerative Clustering):** Nhóm các cổ phiếu theo hành vi tương quan phi tuyến, bóc tách cụm Ngân hàng, Tiêu dùng, Bất động sản và Thép.
2. **Phân Bổ Vốn Động HRP (Hierarchical Risk Parity của Marcos López de Prado):** Tận dụng cây phân cấp để phân bổ vốn theo nghịch đảo phương sai cụm. Tự động ép tỷ trọng các mã giật cục/đầu cơ (họ Vin) về mức an toàn 15% - 18%, và nâng tối đa tỷ trọng (30% - 35%) cho các trụ biến động thấp.
3. **Phòng Vệ Rủi Ro Đuôi (GJR-GARCH Asymmetric Volatility):** Nắm bắt hiệu ứng đòn bẩy biến động. Khi phương sai có điều kiện bùng nổ, tự động siết Trailing Stop từ $2.0 	imes ATR$ về $1.4 	imes ATR$ để né sập sâu.
4. **Vi Cấu Trúc Phái Sinh VN30F1M:** Đo lường độ lệch Basis Spread ($VN30F1M - VN30$). Nếu Basis âm sâu kéo dài $> 2$ phiên $ightarrow$ Cảnh báo "Kéo trụ xả phái sinh", tự động khóa giải ngân.
5. **Khống Chế Trượt Giá Quỹ Vốn Lớn (Almgren-Chriss Impact & 5% ADV20):** Khống chế khối lượng đặt tối đa $\le 5\%$ thanh khoản trung bình 20 phiên, chia nhỏ lệnh theo thuật toán TWAP.

---

## 📁 CẤU TRÚC THƯ MỤC DỰ ÁN

```
vn30_quantitative_trading/
├── data/                               <-- Toàn bộ dữ liệu lịch sử chuẩn hóa (2020 - 2026)
│   ├── 1_market_indices/               (VN-INDEX, VN30, VN30F1M, Ma trận Close & Volume)
│   ├── 2_individual_stocks_vn30/       (30 file CSV chuẩn OHLCV: ACB.csv -> VRE.csv)
│   ├── 3_clustering_and_hrp_models/    (Cụm Ward HAC & Trọng số HRP 90 phiên)
│   ├── 4_performance_and_trade_logs/   (Nhật ký 303 lệnh giao dịch & Báo cáo Fmarket)
│   └── 5_live_execution/               (Phiếu lệnh và trạng thái danh mục hiện tại)
├── docs/                               <-- Tài liệu & Biểu đồ trực quan hóa
│   └── images/                         (Đồ thị so sánh VN-Index, HRP, Dendrogram, Heatmap)
├── hrp_garch_engine.py                 <-- Module toán học HRP & GJR-GARCH(1,1)
├── universe_clustering.py              <-- Thuật toán phân cụm Ward HAC
├── live_order_engine.py                <-- Engine thực thi và quét lệnh thực chiến EOD
├── backtest_hrp_garch_full.py          <-- Kiểm định toàn diện 4 kịch bản 2020 - 2026
├── compare_with_vnindex.py             <-- Đo lường Alpha, Beta, Sharpe so với VN-Index
├── RESEARCH_WALKTHROUGH.md             <-- Toàn bộ 17 chương nghiên cứu chi tiết
├── requirements.txt                    <-- Danh sách thư viện Python
└── .gitignore
```

---

## 🚀 HƯỚNG DẪN CÀI ĐẶT & CHẠY THỰC CHIẾN

### 1. Cài Đặt Môi Trường
```bash
git clone <URL_REPOSITORY_CUA_BAN>
cd vn30_quantitative_trading
pip install -r requirements.txt
```

### 2. Quét Lệnh Thực Chiến Hàng Ngày (Live Execution)
Vào lúc **14:15 – 14:25** mỗi ngày giao dịch, chạy lệnh sau:
```bash
python live_order_engine.py
```
Hệ thống sẽ tự động quét ma trận giá, kiểm tra điều kiện ADX, Basis phái sinh và xuất phiếu lệnh tại:
`data/5_live_execution/daily_order_sheet.csv`

### 3. Chạy Lại Kiểm Định Toàn Chu Kỳ (Backtest)
```bash
python backtest_hrp_garch_full.py
python compare_with_vnindex.py
```

---

## 📜 LICENSE & MIỄN TRỪ TRÁCH NHIỆM
Dự án được phát triển cho mục đích nghiên cứu tài chính định lượng và quản lý danh mục quỹ. Hiệu suất quá khứ không đảm bảo 100% lợi nhuận trong tương lai. Nhà đầu tư cần tuân thủ nghiêm ngặt quy tắc quản trị rủi ro vốn.
