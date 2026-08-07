"""
多時間框架台指期K線資料抓取模組
從 cnyes.com API 獲取資料
"""

import sys
import json
import time
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 設定標準輸出編碼為 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# SSL 信任設定 (避免 SSL Certificate Signature Failure)
SSL_CONTEXT = ssl._create_unverified_context()

# 常數設定
BASE_URL = 'https://ws.api.cnyes.com/ws/api/v1/charting/history'
SYMBOL = 'TWF:TXF:FUTURE'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def convert_cnyes_price(series):
    """
    Cnyes API 偶爾會傳回合成指標比值（如 <100 或 9175），
    將比值還原為真實台指期點位（如 44,500 點）。
    """
    def _convert(x):
        if pd.isna(x):
            return x
        if x < 100:
            return x * 1000
        elif x < 10000:
            return x * 10
        return x
    return series.apply(_convert)

def fetch_kline_yahoo(resolution: str, days_back: int = None) -> pd.DataFrame:
    """
    Yahoo Finance (WTX=F) 備援抓取
    """
    if days_back is None:
        if resolution == 'D': days_back = 180
        elif resolution == '15': days_back = 14
        elif resolution == '5': days_back = 7
        else: days_back = 2
        
    interval_map = {'1': '1m', '5': '5m', '15': '15m', 'D': '1d'}
    interval = interval_map.get(resolution, '1m')
    
    now = int(time.time())
    start_time = now - (days_back * 24 * 60 * 60)
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/WTX=F?symbol=WTX=F&period1={start_time}&period2={now}&interval={interval}"
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            
            result = data.get('chart', {}).get('result', [])
            if not result:
                return pd.DataFrame()
                
            chart_data = result[0]
            timestamps = chart_data.get('timestamp', [])
            indicators = chart_data.get('indicators', {}).get('quote', [{}])[0]
            
            if not timestamps or not indicators:
                return pd.DataFrame()
                
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(timestamps, unit='s', utc=True).tz_convert('Asia/Taipei'),
                'open': indicators.get('open', []),
                'high': indicators.get('high', []),
                'low': indicators.get('low', []),
                'close': indicators.get('close', []),
                'volume': indicators.get('volume', [])
            })
            
            df = df.dropna(subset=['close'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
    except Exception as e:
        print(f"  ⚠️ Yahoo 備援抓取失敗 (resolution={resolution}): {str(e)}")
        return pd.DataFrame()


def fetch_kline(resolution: str, days_back: int = None) -> pd.DataFrame:
    """
    抓取指定時間框架的K線資料 (主要使用 cnyes, 失敗時自動備援 Yahoo)
    
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
        'quote': '1'
    }
    if resolution != 'D':
        params['from'] = start_time
        params['to'] = now
    
    query_string = urllib.parse.urlencode(params)
    url = f"{BASE_URL}?{query_string}"
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as resp:
            raw_data = resp.read().decode('utf-8')
            json_data = json.loads(raw_data)
            
            # 檢查 API 回應狀態
            data_field = json_data.get('data')
            status = json_data.get('s', '')
            if isinstance(data_field, dict):
                status = data_field.get('s', status)
            
            if not data_field or status != 'ok':
                raise ValueError(f"API 回應異常 (status={status})")
            
            data = json_data['data']
            if 't' not in data or not data['t']:
                raise ValueError(f"缺少時間戳")
            
        # 建立 DataFrame
        df = pd.DataFrame({
            'timestamp': pd.to_datetime(data['t'], unit='s', utc=True).tz_convert('Asia/Taipei'),
            'open': data['o'],
            'high': data['h'],
            'low': data['l'],
            'close': data['c'],
            'volume': data['v']
        })
        
        # Cnyes 點位還原防呆
        for col in ['open', 'high', 'low', 'close']:
            df[col] = convert_cnyes_price(df[col])
            
        # 排序與重設索引
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df
        
    except Exception as e:
        print(f"  ⚠️ Cnyes 抓取失敗 ({str(e)})，自動切換至 Yahoo Finance 備援...")
        return fetch_kline_yahoo(resolution, days_back)


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


def fetch_all_timeframes_v2() -> dict:
    """
    抓取所有時間框架的資料，包含 30 分 K（由 5 分 K 重新取樣產生）。
    回傳的 key: 'D', '30', '15', '5', '1'
    
    Returns:
        dict: 包含各個時間框架 DataFrame 的字典
    """
    # 先取得基本四個時間框架
    results = fetch_all_timeframes()
    
    # 產生 30 分 K（由 5 分 K 重新取樣）
    df_5 = results.get('5', pd.DataFrame())
    if not df_5.empty:
        print("  📡 生成 30分K 資料（由 5分K 重新取樣）...")
        results['30'] = resample_df(df_5, '30min')
    else:
        # 若 5 分 K 無資料，嘗試用 15 分 K 重新取樣
        df_15 = results.get('15', pd.DataFrame())
        if not df_15.empty:
            print("  📡 生成 30分K 資料（由 15分K 重新取樣）...")
            results['30'] = resample_df(df_15, '30min')
        else:
            print("  ⚠️ 無法產生 30分K（缺少 5分K 與 15分K 資料）")
            results['30'] = pd.DataFrame()
    
    return results


if __name__ == '__main__':
    price, ts = get_current_price()
    print(f"目前最新價格: {price} 於 {ts}")
    all_data = fetch_all_timeframes_v2()
    for res, df in all_data.items():
        print(f"框架 {res}: 共 {len(df)} 筆資料")
