"""
雙演算法融合轉折點偵測模組 (Hybrid Resonance Box-Fractal Engine)
=============================================================
結合兩大權威演算法之優點:
 1. 日線 (Daily): 採用 Bryce Gilmore 權威雙箱體模型 (鎖定主上點 46,994 / 主下點 40,779) 
    提供穩固的宏觀支撐與壓力防線，不受微觀雜訊干擾。
 2. 15分K / 5分K / 1分K: 採用 Scott Carney 5-Bar Fractal 碎形動態搜尋，
    即時捕捉盤中最新形成的樞紐轉折點，具備極佳的短線敏捷度。
 3. PRZ 共振計算: 當短線 5-Bar 碎形 PRZ 與日線權威箱體 PRZ 重疊時，
    標記為【⭐ 🔥雙模型超級共振 (Super Resonance)】，賦予最高信心水準！
"""

import sys
import pandas as pd
import numpy as np

from swing_detector import detect_swings as detect_fractal_swings
from box_swing_detector import DAILY_MASTER_HIGH, DAILY_MASTER_LOW, WATERLINE

sys.stdout.reconfigure(encoding='utf-8')

def get_hybrid_swings(all_data):
    """
    融合模式：
    - 日線 (D): 使用 Bryce Gilmore 雙箱體模型 (46,994 / 40,779)
    - 15分/5分/1分K: 使用 Scott Carney 5-Bar Fractal 動態搜尋
    """
    results = {}
    
    # 1. 日線 (D) — 採用權威雙箱體模型錨定點
    highs_d = pd.DataFrame([{
        'timestamp': '2026-06-03',
        'price': DAILY_MASTER_HIGH,
        'bar_index': 198
    }])
    lows_d = pd.DataFrame([{
        'timestamp': '2026-06-08',
        'price': DAILY_MASTER_LOW,
        'bar_index': 201
    }])
    
    df_d = all_data.get('D', pd.DataFrame())
    if not df_d.empty and len(df_d) > 10:
        recent = df_d.tail(30)
        recent_max = recent['high'].max()
        recent_min = recent['low'].min()
        highs_d = pd.concat([highs_d, pd.DataFrame([{
            'timestamp': str(recent.loc[recent['high'].idxmax()]['timestamp'])[:10],
            'price': recent_max,
            'bar_index': len(df_d) - 1
        }])], ignore_index=True)
        lows_d = pd.concat([lows_d, pd.DataFrame([{
            'timestamp': str(recent.loc[recent['low'].idxmin()]['timestamp'])[:10],
            'price': recent_min,
            'bar_index': len(df_d) - 1
        }])], ignore_index=True)
        
    results['D'] = {'highs': highs_d, 'lows': lows_d, 'mode_type': 'box_model'}
    
    # 2. 15分K, 5分K, 1分K — 採用 5-Bar Fractal 動態搜尋
    for tf in ['15', '5', '1']:
        df = all_data.get(tf, pd.DataFrame())
        if not df.empty and len(df) >= 5:
            swings = detect_fractal_swings(df, n=2)
            swings['mode_type'] = 'fractal'
            results[tf] = swings
        else:
            results[tf] = {'highs': pd.DataFrame(), 'lows': pd.DataFrame(), 'mode_type': 'fractal'}
            
    return results

def explain_hybrid_model():
    """回傳融合演算法的優點與設計原理"""
    return """
━" * 65
  🔥 雙演算法融合轉折點模型 (Hybrid Box-Fractal Engine) 設計原理
━" * 65

 🧠 一、 為什麼需要融合演算法？
  • 傳統 5-Bar 碎形法：敏捷度極高，能第一時間抓出盤中轉折；但在大行情或單邊趨勢時，
    容易因為微觀 K 線影線過多產生訊號雜訊。
  • 權威雙箱體模型：巨觀大格局極度穩定（錨定日線 46,994 ~ 40,779），但在短線日內交易時，
    可能距離大波段邊界較遠。

 🎯 二、 融合模式三大核心優勢 (The Best of Both Worlds)
  1. 巨觀穩固 (Macro Stability)：
     日線大方向固定採用 Bryce Gilmore 權威雙箱體 (46,994 / 40,779)，確保大格局趨勢判斷與強壓強支撐不偏離。
  2. 微觀敏捷 (Micro Agility)：
     15分K、5分K 與 1分K 採用 Scott Carney 5-Bar Fractal 碎形過濾，即時捕捉最新發生的盤中波段樞紐點。
  3. 超級共振爆發點 (Super Resonance Zone)：
     當短線 5-Bar 碎形計算出來的 PRZ 與日線雙箱體 PRZ (例如 0.382 / 0.618 / 1.130 陷阱區) 
     在相同價位重疊時，系統會自動標記為【⭐ 🔥雙模型超級共振】，為極高勝率之交易轉折契機！
"""
