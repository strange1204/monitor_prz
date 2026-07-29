"""
多時間框架台指期K線資料抓取模組
從 cnyes.com API 獲取資料
"""

import sys
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 設定標準輸出編碼為 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# 常數設定
BASE_URL = 'https://ws.api.cnyes.com/ws/api/v1/charting/history'
SYMBOL = 'TWF:TXF:FUTURE'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def fetch_kline(resolution: str, days_back: int = None) -> pd.DataFrame:
    """
    抓取指定時間框架的K線資料
    
    Args:
        resolution (str): 時間框架 ('1', '5', '15', 'D')
        days_back (int, optional): 回溯天數. 預設值: 分鐘級別1天，日線級別180天.
        
    Returns:
        pd.DataFrame: K線資料，包含 timestamp, open, high, low, close, volume 欄位
    """
    if days_back is None:
        if resolution == 'D':
            days_back = 180
        elif resolution == '15':
            days_back = 14
        elif resolution == '5':
            days_back = 7
        else:
            days_back = 2
        
    # 計算時間範圍 (Unix timestamp)
    now = int(time.time())
    start_time = now - (days_back * 24 * 60 * 60)
    
    # 建立請求參數
    params = {
        'symbol': SYMBOL,
        'resolution': resolution,
        'from': start_time,
        'to': now,
        'quote': '1'
    }
    
    query_string = urllib.parse.urlencode(params)
    url = f"{BASE_URL}?{query_string}"
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_data = resp.read().decode('utf-8')
            json_data = json.loads(raw_data)
            
            # 檢查 API 回應狀態
            data_field = json_data.get('data')
            status = json_data.get('s', '')
            if isinstance(data_field, dict):
                status = data_field.get('s', status)
            
            if not data_field:
                print(f"  ⚠️ API 回應中沒有資料 (resolution={resolution}, status={status})")
                return pd.DataFrame()
            
            data = json_data['data']
            
            # 檢查資料欄位是否存在
            if 't' not in data or not data['t']:
                print(f"  ⚠️ API 資料中缺少時間戳 (resolution={resolution})")
                return pd.DataFrame()
            
        # 建立 DataFrame
        df = pd.DataFrame({
            'timestamp': pd.to_datetime(data['t'], unit='s', utc=True).tz_convert('Asia/Taipei'),
            'open': data['o'],
            'high': data['h'],
            'low': data['l'],
            'close': data['c'],
            'volume': data['v']
        })
        
        # 排序與重設索引
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df
        
    except Exception as e:
        print(f"  ⚠️ 抓取K線資料失敗 (resolution={resolution}): {str(e)}")
        return pd.DataFrame()


def resample_df(df, rule):
    """
    將分鐘K線重新取樣為更大的時間框架

    Args:
        df (pd.DataFrame): 原始K線資料
        rule (str): pandas resample規則 (如 '5min', '15min', '1D')

    Returns:
        pd.DataFrame: 重新取樣後的K線資料
    """
    if df.empty:
        return pd.DataFrame()
    
    resampled = df.set_index('timestamp').resample(rule, label='left', closed='left').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna().reset_index()
    
    return resampled


def get_current_price() -> tuple:
    """
    取得最新一筆1分鐘K線的收盤價與時間
    
    Returns:
        tuple: (最新收盤價, 最新時間)
    """
    df = fetch_kline(resolution='1', days_back=2)
    if not df.empty:
        latest = df.iloc[-1]
        return latest['close'], latest['timestamp']
    return None, None

def fetch_all_timeframes() -> dict:
    """
    抓取所有指定時間框架的資料 (日線, 15分, 5分, 1分)
    若某個時間框架的 API 無資料，嘗試用較小時間框架重新取樣
    
    Returns:
        dict: 包含各個時間框架 DataFrame 的字典
    """
    results = {}
    
    # 先抓取基礎資料（從小到大）
    print("  📡 抓取 1分K 資料...")
    results['1'] = fetch_kline(resolution='1', days_back=2)
    time.sleep(0.3)
    
    print("  📡 抓取 5分K 資料...")
    results['5'] = fetch_kline(resolution='5', days_back=7)
    time.sleep(0.3)
    
    print("  📡 抓取 15分K 資料...")
    results['15'] = fetch_kline(resolution='15', days_back=14)
    time.sleep(0.3)
    
    print("  📡 抓取 日K 資料...")
    results['D'] = fetch_kline(resolution='D', days_back=180)
    time.sleep(0.3)
    
    # 如果 15分K 沒有資料，嘗試用 5分K 或 1分K 重新取樣
    if results['15'].empty and not results['5'].empty:
        print("  🔄 15分K 無資料，使用 5分K 重新取樣...")
        results['15'] = resample_df(results['5'], '15min')
    elif results['15'].empty and not results['1'].empty:
        print("  🔄 15分K 無資料，使用 1分K 重新取樣...")
        results['15'] = resample_df(results['1'], '15min')
    
    # 如果日K沒有資料，嘗試用 5分K 重新取樣
    if results['D'].empty and not results['5'].empty:
        print("  🔄 日K 無資料，使用 5分K 重新取樣...")
        results['D'] = resample_df(results['5'], '1D')
    elif results['D'].empty and not results['15'].empty:
        print("  🔄 日K 無資料，使用 15分K 重新取樣...")
        results['D'] = resample_df(results['15'], '1D')
        
    return results


if __name__ == '__main__':
    price, ts = get_current_price()
    print(f"目前最新價格: {price} 於 {ts}")
    all_data = fetch_all_timeframes()
    for res, df in all_data.items():
        print(f"框架 {res}: 共 {len(df)} 筆資料")
