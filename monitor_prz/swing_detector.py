import sys
import pandas as pd
import numpy as np

# 設置標準輸出編碼為 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

def detect_swing_highs(df, n=2):
    """
    根據Scott Carney的5-Bar Fractal Rule (Williams & Carney Geometric Pivot Filter)檢測Swing High。
    Swing High（波段高點）：當前K線最高價大於左側及右側各n根K線的最高價。
    
    參數:
    df (pd.DataFrame): 包含K線數據的DataFrame，需包含 timestamp, high 欄位
    n (int): 左右兩側需比較的K線數量 (預設為2)
    
    返回:
    pd.DataFrame: 包含合格波段高點的DataFrame，欄位為 timestamp, price, bar_index
    """
    if df.empty or len(df) < (2 * n + 1) or 'high' not in df.columns:
        return pd.DataFrame(columns=['timestamp', 'price', 'bar_index'])
    
    highs = df['high']
    is_swing_high = pd.Series(True, index=df.index)
    
    for i in range(1, n + 1):
        is_swing_high &= (highs > highs.shift(i))
        is_swing_high &= (highs > highs.shift(-i))
        
    int_indices = np.where(is_swing_high)[0]
    
    result = pd.DataFrame({
        'timestamp': df.iloc[int_indices]['timestamp'].values,
        'price': df.iloc[int_indices]['high'].values,
        'bar_index': int_indices
    })
    return result


def detect_swing_lows(df, n=2):
    """
    根據Scott Carney的5-Bar Fractal Rule (Williams & Carney Geometric Pivot Filter)檢測Swing Low。
    Swing Low（波段低點）：當前K線最低價小於左側及右側各n根K線的最低價。
    
    參數:
    df (pd.DataFrame): 包含K線數據的DataFrame，需包含 timestamp, low 欄位
    n (int): 左右兩側需比較的K線數量 (預設為2)
    
    返回:
    pd.DataFrame: 包含合格波段低點的DataFrame，欄位為 timestamp, price, bar_index
    """
    if df.empty or len(df) < (2 * n + 1) or 'low' not in df.columns:
        return pd.DataFrame(columns=['timestamp', 'price', 'bar_index'])
    
    lows = df['low']
    is_swing_low = pd.Series(True, index=df.index)
    
    for i in range(1, n + 1):
        is_swing_low &= (lows < lows.shift(i))
        is_swing_low &= (lows < lows.shift(-i))
        
    int_indices = np.where(is_swing_low)[0]
    
    result = pd.DataFrame({
        'timestamp': df.iloc[int_indices]['timestamp'].values,
        'price': df.iloc[int_indices]['low'].values,
        'bar_index': int_indices
    })
    return result


def detect_swings(df, n=2):
    """
    檢測波段高點與低點。
    
    參數:
    df (pd.DataFrame): 包含K線數據的DataFrame
    n (int): 左右兩側需比較的K線數量 (預設為2)
    
    返回:
    dict: 包含 'highs' 和 'lows' 兩個鍵的字典，值為對應的結果DataFrame
    """
    highs = detect_swing_highs(df, n)
    lows = detect_swing_lows(df, n)
    return {
        'highs': highs,
        'lows': lows
    }


def find_major_swings(df, n=2, top_n=5):
    """
    找出最顯著的波段點 (Master High and Master Low)。
    高點按價格降序排列，低點按價格升序排列，並返回前 top_n 個。
    
    參數:
    df (pd.DataFrame): 包含K線數據的DataFrame
    n (int): 左右兩側需比較的K線數量 (預設為2)
    top_n (int): 要返回的顯著波段點數量
    
    返回:
    dict: 包含 'highs' 和 'lows' 兩個鍵的字典，值為排序並篩選後的DataFrame
    """
    swings = detect_swings(df, n)
    major_highs = swings['highs'].sort_values('price', ascending=False).head(top_n).reset_index(drop=True)
    major_lows = swings['lows'].sort_values('price', ascending=True).head(top_n).reset_index(drop=True)
    
    return {
        'highs': major_highs,
        'lows': major_lows
    }


def get_multi_timeframe_swings(timeframe_data):
    """
    針對多時間框架數據進行波段點檢測。
    
    參數:
    timeframe_data (dict): 鍵為時間框架名稱（例如 'daily', '15min' 等），值為該時間框架對應的DataFrame
    
    返回:
    dict: 鍵為時間框架名稱，值為波段檢測結果字典（包含 'highs' 和 'lows'）
    """
    results = {}
    for tf_name, df in timeframe_data.items():
        results[tf_name] = detect_swings(df, n=2)
        
    return results
