# 🏛️ 台指期 PRZ 諧波交易分析、監控與回測系統 (完整原始開發說明檔 - 本機備份)

> ⚠️ **保密與備份說明**：
> 本檔案為本機專屬備份說明檔 (存放於 `C:\monitor_PRZ\docs\ORIGINAL_PRZ_SYSTEM_README.md`)，
> 包含完整系統架構、演算法數學公式、雙模型超級共振原理、歷史點位由來與模組呼叫指南，用以作為後續版本升級與功能延續之基準依據。

---

## 📁 本機專案完整模組架構

```
C:\monitor_PRZ\
├── docs/
│   └── ORIGINAL_PRZ_SYSTEM_README.md # 本機完整原始開發備份說明檔 (本檔)
├── main.py                           # 原始基礎主程式 (支援互動選單/5-Bar碎形轉折)
├── main_box_prz.py                   # 全功能三合一選單主程式 (支援模式 1/2/3 自由切換)
├── auto_monitor.py                   # 每分鐘即時監控與高信心水準 Email 通報腳本
├── backtest_prz_strategy.py          # 10年期 (2016-2026) 策略遞迴歷史回測與逐年通報引擎
├── data_fetcher.py                   # API 數據抓取 (日K/15分K/5分K/1分K 235根K線完整載入)
├── swing_detector.py                 # Scott Carney 5-Bar Fractal 碎形轉折點過濾模組
├── box_swing_detector.py             # Bryce Gilmore 雙箱體結構模型 (鎖定 46,994 / 40,779)
├── hybrid_swing_detector.py          # 🔥 雙演算法優點融合超級共振引擎 (Mode 3 推薦首選)
├── prz_calculator.py                 # PRZ 黃金分割與價位去重/共振組合計算引擎
├── trade_advisor.py                  # 結合日線大方向之交易建議與 3 階停損停利生成器
├── notifier.py                       # Gmail SMTP Email 通報模組 (strange751204 -> brian555878)
├── sync_github.py                    # 本地 Git Commit 與 GitHub 自動同步腳本
└── .github/workflows/
    ├── auto_monitor.yml              # GitHub Actions 24/7 雲端 1 分鐘高頻即時監控
    └── backtest.yml                  # GitHub Actions 10年期雲端回測與 Artifact 暫存
```

---

## 🧠 核心演算法理論與點位由來

### 1. 日線權威雙箱體點位由來 (`46,994` 與 `40,779`)
- **主上點 (`46,994`)**：2026年06月03日 創下之大波段極限頂部高點！爆量倒 V 轉折形成日線級別超級強壓水線 (Upper Box Peak)。
- **主下點 (`40,779`)**：2026年06月08日 急殺波段之恐慌極限低點！觸發 1.130 洗盤陷阱極限 V 轉強彈，形成日線級別超級強支撐箱底 (Lower Box Base)。
- **中間分界水線 (Waterline)**：$43,886.5$ (箱體高度 $\Delta H = 6,215$ 點，劃分為 3,107 點之上下兩等高箱體)。

### 2. 三大轉折點計算模式 (Swing Pivot Models)
- **【模式 1】Scott Carney 5-Bar Fractal 碎形法**：動態搜尋多時間框架左右各 2 根包夾之局部轉折點，短線敏捷度高。
- **【模式 2】Bryce Gilmore 權威雙箱體模型**：日線固定鎖定 `46,994` / `40,779`，提供穩固的跨週/跨月大格局防線。
- **【模式 3】🔥 雙演算法優點融合模式 (Hybrid Resonance Box-Fractal Engine)**：
  - 日線 (Daily) 鎖定權威雙箱體 (`46,994` / `40,779`) 提供宏觀防線。
  - 15分/5分/1分K 採用 5-Bar 碎形動態搜尋。
  - 當短線碎形 PRZ 與日線權威箱體 PRZ 於同價位重疊時，觸發 **`[🔥雙模型超級共振]`**！

### 3. PRZ 黃金分割係數表
- **回撤位 (Retracement)**：`0.236` (淺層), `0.382` (標準), `0.500` (中心水線), `0.618` (黃金分割), `0.786` (加特利位), `0.886` (蝙蝠極限位)
- **延伸位 (Extension)**：`1.130` (假突破洗盤陷阱區), `1.272` (蝴蝶延伸位), `1.618` (螃蟹極限位)

---

## 💻 本機常用執行指令指南

### 1. 執行三合一選單主程式
```bash
python main_box_prz.py
```
*(可傳入參數 `--mode 1/2/3` 與 `--position long/short`)*

### 2. 啟動本機每分鐘即時監控
```bash
python auto_monitor.py
```

### 3. 執行 10 年期 (2016-2026) 遞迴歷史回測
```bash
python backtest_prz_strategy.py
```

### 4. 同步更新至 GitHub
```bash
python sync_github.py
```

---

## 🛡️ 歷史回測保護機制 (3-Strike Rule Guard)

回測模組 `backtest_prz_strategy.py` 內建 `StepErrorTracker`。若在「數據抓取」、「轉折點過濾」、「PRZ計算」、「交易模擬」任一步驟中累積失敗達 **3 次**，系統將拋出 `StepBottleneckException` **自動中斷保護**，並跳出問題分析與討論提示。

---

*本備份說明檔建立時間：2026-07-30 | 專屬保存於 C:\monitor_PRZ\docs\*
