# 🏛️ 台指期 PRZ 諧波交易分析與點位預測系統

本系統基於 **Scott M. Carney** 的 **Harmonic Trading（諧波交易）** 權威理論與 **Bryce Gilmore** 的多時間框架箱體模型，為台指期（TXF）提供即時 PRZ（Potential Reversal Zone，潛在反轉區）計算、多時間框架轉折點偵測、進出場與停損停利建議，並支援 Email 警報與 GitHub 自動同步。

---

## 📁 專案架構

```
C:\monitor_PRZ\
├── main.py            # 主程式入口（支援命令列與互動選單選單）
├── data_fetcher.py    # K線數據抓取模組 (日K / 15分K / 5分K / 1分K)
├── swing_detector.py  # Scott Carney 5-Bar Fractal Rule 樞紐轉折偵測
├── prz_calculator.py  # PRZ 黃金分割與多時間框架共振計算引擎
├── trade_advisor.py   # 交易與停損停利建議生成器（多單/空單各至少3個位階）
├── notifier.py        # Gmail SMTP Email 通知與警報發送模組
├── sync_github.py     # GitHub 自動同步腳本 (https://github.com/strange1204/monitor_prz.git)
├── monitor_prz/       # 同步備份資料夾
└── requirements.txt   # 相依套件 (pandas, numpy)
```

---

## 🚀 快速開始

### 1. 安裝套件
```bash
pip install -r requirements.txt
```

### 2. 執行主程式

- **互動選單模式 (選單操作)**:
  ```bash
  python main.py --interactive
  ```

- **全盤趨勢分析 (無部位時)**:
  ```bash
  python main.py
  ```

- **手上有【多單】時 (計算多單 3 個停損與 3 個停利位)**:
  ```bash
  python main.py --position long
  ```

- **手上有【空單】時 (計算空單 3 個停損與 3 個停利位)**:
  ```bash
  python main.py --position short
  ```

- **發送即時分析報告至 Email**:
  ```bash
  python main.py --email
  ```

- **查看 PRZ 理論依據說明**:
  ```bash
  python main.py --theory
  ```

---

## 📖 PRZ 黃金分割係數理論基礎

| 類型 | 比率 | 名稱 / 數學由來 | 實戰說明 |
|------|------|-----------------|----------|
| 回撤 | `0.236` | 淺層回撤 (Φ⁻³) | 飆漲/急跌段強勢整理區 |
| 回撤 | `0.382` | 標準回撤 (Φ⁻²) | 初階拉回防衛線 |
| 回撤 | `0.500` | 中心回撤 | 箱體對稱中點 |
| 回撤 | `0.618` | 深度回撤 (Φ⁻¹) | 黃金關鍵分割防線 |
| 回撤 | `0.786` | 加特利位 (√0.618) | Gartley Pattern 核心防線 |
| 回撤 | `0.886` | 蝙蝠極限位 (√0.786) | Bat Pattern 極限反轉區 |
| 延伸 | `1.130` | 陷阱區 (⁴√1.618) | 假突破/假跌破多空洗盤陷阱區 |
| 延伸 | `1.272` | 蝴蝶延伸 (√1.618) | Butterfly Pattern 初階測幅 |
| 延伸 | `1.618` | 螃蟹延伸 (Φ) | Crab Pattern 極限爆發區 |

> 📚 創始權威文獻：
> 1. Scott M. Carney - *Harmonic Trading Volume 1 & Volume 2*
> 2. Larry Pesavento - *Fibonacci Ratios with Pattern Recognition*
> 3. Bryce Gilmore - *Geometry of Stock Market Wave Ratios*

---

## 📤 GitHub 同步

執行以下指令，即可自動提交並推送到 [https://github.com/strange1204/monitor_prz.git](https://github.com/strange1204/monitor_prz.git)：
```bash
python sync_github.py
```
