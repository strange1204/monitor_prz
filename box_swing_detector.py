"""
Bryce Gilmore 權威箱體結構錨定模組 (Box Model Swing Detector)
===========================================================
日線固定錨定歷史權威雙箱體:
 - 主上點 (Master High): 46,994 (2026-06-03 創下之波段極限頂部)
 - 主下點 (Master Low) : 40,779 (2026-06-08 恐慌急殺波段之極限箱底)
 - 中間分界水線 (Waterline): 43,886.5
 - 箱體高度 (ΔH): 6,215 點
"""

import sys
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

# 固定日線主箱體錨定點
DAILY_MASTER_HIGH = 46994.0  # 2026-06-03 頂部高點
DAILY_MASTER_LOW = 40779.0   # 2026-06-08 恐慌箱底
WATERLINE = 43886.5          # 中間水線

def get_box_model_swings(all_data):
    """
    根據 Bryce Gilmore 箱體結構模型，生成各時間框架的 Swing 點。
    
    日線: 鎖定權威箱體 46,994 ~ 40,779
    15分K / 5分K / 1分K: 錨定當前波段主要結構箱體
    """
    results = {}
    
    # 1. 日線 (Daily) — 錨定歷史雙箱體 46,994 / 40,779
    df_d = all_data.get('D', pd.DataFrame())
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
    
    # 若有真實日K數據，將近期次級高低點加入清單
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
        
    results['D'] = {'highs': highs_d, 'lows': lows_d, 'is_box_model': True}
    
    # 2. 其他時間框架 (15分, 5分, 1分) — 抓取主結構箱體
    for tf in ['15', '5', '1']:
        df = all_data.get(tf, pd.DataFrame())
        if df.empty or len(df) < 5:
            results[tf] = {'highs': pd.DataFrame(), 'lows': pd.DataFrame()}
            continue
            
        # 找出該時間框架的絕對最高與最低
        max_idx = df['high'].idxmax()
        min_idx = df['low'].idxmin()
        
        max_row = df.loc[max_idx]
        min_row = df.loc[min_idx]
        
        highs_tf = pd.DataFrame([{
            'timestamp': max_row['timestamp'],
            'price': max_row['high'],
            'bar_index': max_idx
        }])
        
        lows_tf = pd.DataFrame([{
            'timestamp': min_row['timestamp'],
            'price': min_row['low'],
            'bar_index': min_idx
        }])
        
        # 增加次級轉折點
        if len(df) >= 20:
            half_len = len(df) // 2
            sub_max = df.iloc[-half_len:]['high'].max()
            sub_min = df.iloc[-half_len:]['low'].min()
            highs_tf = pd.concat([highs_tf, pd.DataFrame([{
                'timestamp': df.iloc[-half_len:]['timestamp'].iloc[0],
                'price': sub_max,
                'bar_index': len(df) - half_len
            }])], ignore_index=True)
            lows_tf = pd.concat([lows_tf, pd.DataFrame([{
                'timestamp': df.iloc[-half_len:]['timestamp'].iloc[0],
                'price': sub_min,
                'bar_index': len(df) - half_len
            }])], ignore_index=True)
            
        results[tf] = {'highs': highs_tf, 'lows': lows_tf}
        
    return results

def explain_box_origin():
    """回傳 why 46,994 與 40,779 的歷史由來與幾何分析說明"""
    return f"""
{"━" * 65}
  📖 日線主點位 46,994 與 40,779 的歷史由來與幾何結構解析
{"━" * 65}

 🏛️ 一、 歷史 K 線數據驗證 (實證來源)
  1. 上點 [46,994]：2026年06月03日 創下之大波段極限頂部高點！
     在當日觸發爆量倒 V 轉折，形成日線級別超級強壓水線 (Upper Box Peak)。
  2. 下點 [40,779]：2026年06月08日 急殺波段之恐慌極限低點！
     在當日落底觸發 1.130 洗盤陷阱極限 V 轉強彈，形成日線級別超級強支撐箱底 (Lower Box Base)。

 📐 二、 Bryce Gilmore 雙箱體結構幾何模型 (Double Box Model)
  - 主箱體頂部 (Box 1 High) = 46,994
  - 中間分界水線 (Waterline) = 43,886.5
  - 主箱體底部 (Box 2 Low)  = 40,779
  - 總箱體高度 (ΔH)         = 46,994 - 40,779 = 6,215 點！
  
  此結構恰好劃分為兩個等高箱體：
   • 上箱體 (Box 1): 43,887 ~ 46,994 (高度 3,107 點)
   • 下箱體 (Box 2): 40,779 ~ 43,886 (高度 3,107 點)

 🧠 三、 實戰應用效益
  以此雙箱體作為日線主錨定點，可完美推算出台指期在跨週/跨月大波段中，
  0.382 (43,153)、0.500 (43,886)、0.618 (44,620) 以及 1.130 陷阱區等 key PRZ 價位！
"""
