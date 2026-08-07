"""
🏛️ PRZ V2 台指期整合分析系統
=============================
一站式整合分析主程式，融合：
  1. BoxZoneEngine — 雙箱體區間定位與勝率引擎
  2. MultiTFTrendScanner — 多時間框架 K 線趨勢掃描 (1分/5分/15分/30分K)
  3. IndicatorEngine — RSI(14) 與成交量指標分析
  4. PRZ Matrix — PRZ 黃金分割價位矩陣計算
  5. SmartAdvisor — 智慧建議引擎（同時輸出做多/做空方案含勝率與信心水準）

Usage:
  python prz_v2_analyzer.py                          # 空手查詢
  python prz_v2_analyzer.py --price 44245             # 指定點位查詢
  python prz_v2_analyzer.py --position long --cost 42711   # 持有多單
  python prz_v2_analyzer.py --position short --cost 43886  # 持有空單
"""

import sys
import os
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')

# ─── 導入現有模組 ───
from data_fetcher import fetch_all_timeframes_v2, get_current_price, fetch_kline
from swing_detector import detect_swings as detect_fractal_swings
from box_swing_detector import DAILY_MASTER_HIGH, DAILY_MASTER_LOW, WATERLINE
from prz_calculator import (
    calculate_prz_levels,
    calculate_multi_timeframe_prz,
    group_prz_levels,
    get_grouped_nearby_prz,
    FIB_RATIOS
)

# ═══════════════════════════════════════════════════════════════════
#  常數定義
# ═══════════════════════════════════════════════════════════════════

# Bryce Gilmore 權威雙箱體常數
MASTER_HIGH = DAILY_MASTER_HIGH    # 46,994
MASTER_LOW  = DAILY_MASTER_LOW     # 40,779
WATER_LINE  = WATERLINE            # 43,886.5
BOX_HEIGHT  = MASTER_HIGH - MASTER_LOW  # 6,215

# 上箱 / 下箱定義
UPPER_BOX_TOP    = MASTER_HIGH     # 46,994
UPPER_BOX_BOTTOM = WATER_LINE      # 43,886.5
LOWER_BOX_TOP    = WATER_LINE      # 43,886.5
LOWER_BOX_BOTTOM = MASTER_LOW      # 40,779

# 時間框架名稱對照
TF_DISPLAY = {
    '1':  '1分K',
    '5':  '5分K',
    '15': '15分K',
    '30': '30分K',
    'D':  '日K',
}

# 趨勢 emoji 對照
TREND_EMOJI = {
    '偏多': '🟢',
    '偏空': '🔴',
    '中性': '🟡',
}


# ═══════════════════════════════════════════════════════════════════
#  1. BoxZoneEngine — 雙箱體區間定位與勝率引擎
# ═══════════════════════════════════════════════════════════════════

class BoxZoneEngine:
    """
    判斷現價在雙箱體中的相對位置，並推估做多/做空勝率。
    
    規則：
    - 靠近區間下緣 → 做多勝率高 (65%~80%)
    - 靠近區間上緣 → 做空勝率高 (65%~80%)
    - 區間中間位置 → 多空均勢 (~50%)
    """
    
    def __init__(self):
        self.upper_box = (UPPER_BOX_BOTTOM, UPPER_BOX_TOP)  # 43,886.5 ~ 46,994
        self.lower_box = (LOWER_BOX_BOTTOM, LOWER_BOX_TOP)  # 40,779 ~ 43,886.5
    
    def locate_price(self, price):
        """
        判斷現價所在的箱體與相對位置。
        回傳: dict { box_name, box_range, position_pct, position_desc }
        """
        if price >= self.upper_box[0]:
            # 在上箱 (或已突破上箱)
            box_name = '上箱'
            box_range = self.upper_box
            box_height = box_range[1] - box_range[0]
            position_pct = (price - box_range[0]) / box_height if box_height > 0 else 0.5
            position_pct = max(0.0, min(1.0, position_pct))
        else:
            # 在下箱 (或已跌破下箱)
            box_name = '下箱'
            box_range = self.lower_box
            box_height = box_range[1] - box_range[0]
            position_pct = (price - box_range[0]) / box_height if box_height > 0 else 0.5
            position_pct = max(0.0, min(1.0, position_pct))
        
        # 位置描述
        if position_pct <= 0.25:
            position_desc = '偏向下緣'
        elif position_pct <= 0.45:
            position_desc = '中下區域'
        elif position_pct <= 0.55:
            position_desc = '中間水線附近'
        elif position_pct <= 0.75:
            position_desc = '中上區域'
        else:
            position_desc = '偏向上緣'
        
        return {
            'box_name': box_name,
            'box_range': box_range,
            'position_pct': position_pct,
            'position_desc': position_desc,
        }
    
    def estimate_win_rate(self, price, trend_bias=0.0):
        """
        根據價格在箱體中的位置，推估做多/做空勝率。
        
        trend_bias: -1.0 ~ +1.0, 正值偏多、負值偏空（由趨勢掃描引擎提供）
        
        勝率計算邏輯:
        - position_pct 靠近 0 (下緣)：做多勝率高
        - position_pct 靠近 1 (上緣)：做空勝率高
        - 中間：多空均勢
        """
        loc = self.locate_price(price)
        pct = loc['position_pct']
        
        # 基礎勝率：以 position_pct 線性映射
        # pct=0 → 做多 80%, 做空 20%
        # pct=0.5 → 做多 50%, 做空 50%
        # pct=1 → 做多 20%, 做空 80%
        base_long_wr  = 0.80 - 0.60 * pct   # 0.80 → 0.20
        base_short_wr = 0.20 + 0.60 * pct   # 0.20 → 0.80
        
        # 趨勢調整 (最多 ±10%)
        trend_adj = trend_bias * 0.10
        long_wr  = max(0.15, min(0.85, base_long_wr + trend_adj))
        short_wr = max(0.15, min(0.85, base_short_wr - trend_adj))
        
        return {
            'long_win_rate':  round(long_wr * 100, 1),
            'short_win_rate': round(short_wr * 100, 1),
            'location': loc,
        }
    
    def check_5min_breakout(self, df_5min, threshold=3):
        """
        檢查 5 分 K 是否連續 N 根站上/跌破箱體邊界。
        
        - 連續 3 根收盤站上 MASTER_HIGH → 突破上箱
        - 連續 3 根收盤跌破 MASTER_LOW  → 跌破下箱
        - 連續 3 根收盤站上 WATER_LINE  → 突破水線向上
        - 連續 3 根收盤跌破 WATER_LINE  → 跌破水線向下
        """
        result = {
            'break_upper': False,
            'break_lower': False,
            'break_waterline_up': False,
            'break_waterline_down': False,
            'detail': '尚未觸發任何突破'
        }
        
        if df_5min is None or df_5min.empty or len(df_5min) < threshold:
            return result
        
        recent = df_5min.tail(threshold)['close'].values
        
        # 連續 3 根站上 MASTER_HIGH
        if all(c > MASTER_HIGH for c in recent):
            result['break_upper'] = True
            result['detail'] = f'⚡ 5分K 連續 {threshold} 根收盤站上 {MASTER_HIGH:,.0f}！有效突破上箱！'
        
        # 連續 3 根跌破 MASTER_LOW
        if all(c < MASTER_LOW for c in recent):
            result['break_lower'] = True
            result['detail'] = f'⚡ 5分K 連續 {threshold} 根收盤跌破 {MASTER_LOW:,.0f}！有效跌破下箱！'
        
        # 連續 3 根站上水線
        if all(c > WATER_LINE for c in recent):
            result['break_waterline_up'] = True
            if not result['break_upper']:
                result['detail'] = f'📈 5分K 連續 {threshold} 根站上水線 {WATER_LINE:,.1f}，偏多結構確立'
        
        # 連續 3 根跌破水線
        if all(c < WATER_LINE for c in recent):
            result['break_waterline_down'] = True
            if not result['break_lower']:
                result['detail'] = f'📉 5分K 連續 {threshold} 根跌破水線 {WATER_LINE:,.1f}，偏空結構確立'
        
        return result


# ═══════════════════════════════════════════════════════════════════
#  2. MultiTFTrendScanner — 多時間框架 K 線趨勢掃描
# ═══════════════════════════════════════════════════════════════════

class MultiTFTrendScanner:
    """
    掃描 1分/5分/15分/30分K 的趨勢方向。
    判斷依據：最近兩組 Swing High/Low 是否呈現上升/下降排列。
    """
    
    def scan(self, all_data):
        """
        掃描所有時間框架趨勢。
        
        Returns:
            dict: { tf: { trend, highs, lows } }
        """
        results = {}
        bull_score = 0
        bear_score = 0
        
        for tf in ['1', '5', '15', '30']:
            df = all_data.get(tf, pd.DataFrame())
            if df.empty or len(df) < 5:
                results[tf] = {'trend': '中性', 'highs': [], 'lows': []}
                continue
            
            swings = detect_fractal_swings(df, n=2)
            highs_df = swings.get('highs', pd.DataFrame())
            lows_df = swings.get('lows', pd.DataFrame())
            
            highs = sorted(highs_df['price'].tolist()) if not highs_df.empty else []
            lows = sorted(lows_df['price'].tolist()) if not lows_df.empty else []
            
            # 取最近的兩個高點與兩個低點（按 bar_index 排序）
            trend = '中性'
            if not highs_df.empty and not lows_df.empty:
                recent_highs = highs_df.sort_values('bar_index').tail(2)
                recent_lows = lows_df.sort_values('bar_index').tail(2)
                
                if len(recent_highs) >= 2 and len(recent_lows) >= 2:
                    h_vals = recent_highs['price'].values
                    l_vals = recent_lows['price'].values
                    
                    if h_vals[-1] > h_vals[-2] and l_vals[-1] > l_vals[-2]:
                        trend = '偏多'
                        weight = 2 if tf == '30' else 1
                        bull_score += weight
                    elif h_vals[-1] < h_vals[-2] and l_vals[-1] < l_vals[-2]:
                        trend = '偏空'
                        weight = 2 if tf == '30' else 1
                        bear_score += weight
            
            results[tf] = {
                'trend': trend,
                'highs': highs_df if not highs_df.empty else pd.DataFrame(),
                'lows': lows_df if not lows_df.empty else pd.DataFrame(),
            }
        
        # 計算趨勢偏差值 (-1.0 ~ +1.0)
        total = bull_score + bear_score
        if total > 0:
            trend_bias = (bull_score - bear_score) / max(total, 1)
        else:
            trend_bias = 0.0
        
        # 整體趨勢
        if bull_score > bear_score:
            overall = '偏多'
        elif bear_score > bull_score:
            overall = '偏空'
        else:
            overall = '中性'
        
        return {
            'timeframes': results,
            'overall': overall,
            'trend_bias': trend_bias,
            'bull_score': bull_score,
            'bear_score': bear_score,
        }


# ═══════════════════════════════════════════════════════════════════
#  3. IndicatorEngine — RSI(14) 與成交量分析
# ═══════════════════════════════════════════════════════════════════

class IndicatorEngine:
    """
    計算各時間框架的 RSI(14) 與成交量分析。
    """
    
    @staticmethod
    def calculate_rsi(df, period=14):
        """
        計算 RSI(14)。
        """
        if df is None or df.empty or len(df) < period + 1:
            return None
        
        close = df['close'].values
        deltas = np.diff(close)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        if len(gains) < period:
            return None
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 2)
    
    @staticmethod
    def analyze_volume(df, lookback=5):
        """
        分析最新一根 K 棒的成交量 vs 近 N 根均量。
        """
        if df is None or df.empty or len(df) < lookback + 1:
            return {'status': '無資料', 'ratio': None}
        
        latest_vol = df['volume'].iloc[-1]
        avg_vol = df['volume'].iloc[-(lookback+1):-1].mean()
        
        if avg_vol == 0:
            return {'status': '無資料', 'ratio': None}
        
        ratio = latest_vol / avg_vol
        
        if ratio >= 2.0:
            status = '🔺 爆量'
        elif ratio >= 1.3:
            status = '📈 放量'
        elif ratio >= 0.7:
            status = '📊 正常'
        else:
            status = '📉 縮量'
        
        return {'status': status, 'ratio': round(ratio, 2)}
    
    def scan_all(self, all_data):
        """
        掃描所有時間框架的 RSI 與成交量。
        """
        results = {}
        for tf in ['1', '5', '15', '30']:
            df = all_data.get(tf, pd.DataFrame())
            rsi = self.calculate_rsi(df) if not df.empty else None
            vol = self.analyze_volume(df) if not df.empty else {'status': '無資料', 'ratio': None}
            
            # RSI 狀態判定
            if rsi is not None:
                if rsi >= 80:
                    rsi_status = '極度超買'
                elif rsi >= 70:
                    rsi_status = '超買區'
                elif rsi <= 20:
                    rsi_status = '極度超賣'
                elif rsi <= 30:
                    rsi_status = '超賣區'
                else:
                    rsi_status = '中性'
            else:
                rsi_status = '無資料'
            
            results[tf] = {
                'rsi': rsi,
                'rsi_status': rsi_status,
                'volume': vol,
            }
        
        return results


# ═══════════════════════════════════════════════════════════════════
#  4. PRZ Matrix — PRZ 價位矩陣計算引擎
# ═══════════════════════════════════════════════════════════════════

class PRZMatrixEngine:
    """
    計算多時間框架 PRZ 價位矩陣。
    - 日線：固定錨定權威箱體 46,994 / 40,779
    - 15分/5分/1分K：動態 5-Bar Fractal 偵測 Swing High/Low
    """
    
    def calculate(self, all_data, trend_scan_results, current_price):
        """
        計算完整 PRZ 矩陣。
        
        Returns:
            dict: {
                'all_prz': list,       # 所有 PRZ 水位（已分組去重）
                'nearby': dict,        # 上方/下方最近 PRZ
                'raw_prz': list,       # 原始 PRZ（未分組）
                'swing_pairs': dict,   # 各時間框架的 swing pair
            }
        """
        tf_pairs = {}
        
        # 1. 日線 — 權威箱體固定錨定
        tf_pairs['日K(權威箱體)'] = (MASTER_HIGH, MASTER_LOW)
        
        # 2. 短線時間框架 — 5-Bar Fractal
        for tf in ['15', '5', '1']:
            tf_data = trend_scan_results.get('timeframes', {}).get(tf, {})
            highs_df = tf_data.get('highs', pd.DataFrame())
            lows_df = tf_data.get('lows', pd.DataFrame())
            
            if isinstance(highs_df, pd.DataFrame) and not highs_df.empty and \
               isinstance(lows_df, pd.DataFrame) and not lows_df.empty:
                master_high = highs_df['price'].max()
                master_low = lows_df['price'].min()
                if master_high > master_low:
                    tf_name = TF_DISPLAY.get(tf, tf)
                    tf_pairs[tf_name] = (master_high, master_low)
        
        # 3. 計算所有 PRZ 水位
        raw_prz = calculate_multi_timeframe_prz(tf_pairs)
        
        # 4. 分組去重與共振偵測
        grouped_prz = group_prz_levels(raw_prz, tolerance_points=3.0)
        
        # 5. 找出近端 PRZ
        nearby = get_grouped_nearby_prz(current_price, grouped_prz, n_min=3)
        
        return {
            'all_prz': grouped_prz,
            'nearby': nearby,
            'raw_prz': raw_prz,
            'swing_pairs': tf_pairs,
        }


# ═══════════════════════════════════════════════════════════════════
#  5. SmartAdvisor — 智慧建議引擎
# ═══════════════════════════════════════════════════════════════════

class SmartAdvisor:
    """
    綜合所有引擎結論，同時輸出做多與做空方案。
    """
    
    def generate_both_sides(self, current_price, nearby_prz, indicator_results,
                            box_win_rates, breakout_info, trend_scan):
        """
        同時產生做多方案與做空方案。
        
        Returns:
            dict: { 'long': {...}, 'short': {...}, 'summary': {...} }
        """
        long_plan = self._generate_long_plan(current_price, nearby_prz, indicator_results,
                                              box_win_rates, breakout_info, trend_scan)
        short_plan = self._generate_short_plan(current_price, nearby_prz, indicator_results,
                                                box_win_rates, breakout_info, trend_scan)
        summary = self._generate_summary(long_plan, short_plan, breakout_info, trend_scan)
        
        return {
            'long': long_plan,
            'short': short_plan,
            'summary': summary,
        }
    
    def generate_position_advice(self, current_price, nearby_prz, indicator_results,
                                  box_win_rates, breakout_info, trend_scan,
                                  position_type, cost_price):
        """
        為持倉用戶產生專屬建議。
        """
        if position_type == 'long':
            plan = self._generate_long_plan(current_price, nearby_prz, indicator_results,
                                             box_win_rates, breakout_info, trend_scan)
            pnl = current_price - cost_price
            plan['pnl'] = pnl
            plan['cost'] = cost_price
            return {'position': plan, 'type': '多單'}
        else:
            plan = self._generate_short_plan(current_price, nearby_prz, indicator_results,
                                              box_win_rates, breakout_info, trend_scan)
            pnl = cost_price - current_price
            plan['pnl'] = pnl
            plan['cost'] = cost_price
            return {'position': plan, 'type': '空單'}
    
    def _determine_confidence(self, win_rate, has_resonance, rsi_favorable):
        """根據勝率與條件判定信心水準"""
        score = 0
        if win_rate >= 65:
            score += 2
        elif win_rate >= 55:
            score += 1
        
        if has_resonance:
            score += 1
        if rsi_favorable:
            score += 1
        
        if score >= 3:
            return '🔥高'
        elif score >= 2:
            return '⚡中'
        else:
            return '🛡️低'
    
    def _generate_long_plan(self, current_price, nearby_prz, indicators, 
                             box_wr, breakout, trend_scan):
        """產生做多方案"""
        win_rate = box_wr['long_win_rate']
        
        # 進場區間：以最近的下方支撐 PRZ 為基準
        below = nearby_prz.get('below', [])
        above = nearby_prz.get('above', [])
        
        # 尋找進場區間
        if below:
            nearest_support = below[0]  # 最近的下方支撐
            entry_low = nearest_support['price']
            entry_high = min(current_price, entry_low + 50)
        else:
            entry_low = current_price - 30
            entry_high = current_price
        
        # 停損：取下方 PRZ 的 3 個位階
        stop_losses = []
        SL_OFFSET = 20
        labels = ['保守', '標準', '積極']
        seen = set()
        for i, lvl in enumerate(below):
            p = lvl['price']
            rounded = round(p)
            if rounded not in seen and i < 3:
                seen.add(rounded)
                sl_price = p - SL_OFFSET
                dist = round(current_price - sl_price)
                stop_losses.append({
                    'label': labels[min(i, 2)],
                    'price': round(sl_price),
                    'distance': dist,
                    'pct': round(dist / current_price * 100, 2),
                    'prz_info': ' | '.join(lvl.get('combo_details', [])[:2]),
                })
        
        # 停利：取上方 PRZ 的 3 個位階
        take_profits = []
        seen = set()
        for i, lvl in enumerate(above):
            p = lvl['price']
            rounded = round(p)
            if rounded not in seen and i < 3:
                seen.add(rounded)
                dist = round(p - current_price)
                take_profits.append({
                    'label': labels[min(i, 2)],
                    'price': round(p),
                    'distance': dist,
                    'pct': round(dist / current_price * 100, 2),
                    'prz_info': ' | '.join(lvl.get('combo_details', [])[:2]),
                })
        
        # RSI 判定
        rsi_1m = indicators.get('1', {}).get('rsi')
        rsi_favorable = rsi_1m is not None and rsi_1m < 40
        has_resonance = any(lvl.get('is_resonance', False) for lvl in below[:2])
        
        confidence = self._determine_confidence(win_rate, has_resonance, rsi_favorable)
        
        # 建議理由
        loc = box_wr['location']
        reasons = []
        reasons.append(f"現價位於{loc['box_name']}{loc['position_desc']}")
        if trend_scan['overall'] != '中性':
            reasons.append(f"多時間框架綜合趨勢 {trend_scan['overall']}")
        if rsi_1m is not None:
            reasons.append(f"1分K RSI({rsi_1m:.1f})")
        if has_resonance:
            reasons.append("近端有共振支撐")
        
        return {
            'direction': '做多',
            'win_rate': win_rate,
            'confidence': confidence,
            'entry_zone': (round(entry_low), round(entry_high)),
            'stop_loss': stop_losses,
            'take_profit': take_profits,
            'reason': '，'.join(reasons),
            'current_price': current_price,
            'nearby_prz': nearby_prz,
        }
    
    def _generate_short_plan(self, current_price, nearby_prz, indicators,
                              box_wr, breakout, trend_scan):
        """產生做空方案"""
        win_rate = box_wr['short_win_rate']
        
        above = nearby_prz.get('above', [])
        below = nearby_prz.get('below', [])
        
        # 進場區間：以最近的上方壓力 PRZ 為基準
        if above:
            nearest_resistance = above[0]
            entry_high = nearest_resistance['price']
            entry_low = max(current_price, entry_high - 50)
        else:
            entry_low = current_price
            entry_high = current_price + 30
        
        # 停損：取上方 PRZ 的 3 個位階
        stop_losses = []
        SL_OFFSET = 20
        labels = ['保守', '標準', '積極']
        seen = set()
        for i, lvl in enumerate(above):
            p = lvl['price']
            rounded = round(p)
            if rounded not in seen and i < 3:
                seen.add(rounded)
                sl_price = p + SL_OFFSET
                dist = round(sl_price - current_price)
                stop_losses.append({
                    'label': labels[min(i, 2)],
                    'price': round(sl_price),
                    'distance': dist,
                    'pct': round(dist / current_price * 100, 2),
                    'prz_info': ' | '.join(lvl.get('combo_details', [])[:2]),
                })
        
        # 停利：取下方 PRZ 的 3 個位階
        take_profits = []
        seen = set()
        for i, lvl in enumerate(below):
            p = lvl['price']
            rounded = round(p)
            if rounded not in seen and i < 3:
                seen.add(rounded)
                dist = round(current_price - p)
                take_profits.append({
                    'label': labels[min(i, 2)],
                    'price': round(p),
                    'distance': dist,
                    'pct': round(dist / current_price * 100, 2),
                    'prz_info': ' | '.join(lvl.get('combo_details', [])[:2]),
                })
        
        # RSI 判定
        rsi_1m = indicators.get('1', {}).get('rsi')
        rsi_favorable = rsi_1m is not None and rsi_1m > 60
        has_resonance = any(lvl.get('is_resonance', False) for lvl in above[:2])
        
        confidence = self._determine_confidence(win_rate, has_resonance, rsi_favorable)
        
        # 建議理由
        loc = box_wr['location']
        reasons = []
        reasons.append(f"現價位於{loc['box_name']}{loc['position_desc']}")
        if trend_scan['overall'] != '中性':
            reasons.append(f"多時間框架綜合趨勢 {trend_scan['overall']}")
        if rsi_1m is not None:
            reasons.append(f"1分K RSI({rsi_1m:.1f})")
        if has_resonance:
            reasons.append("近端有共振壓力")
        
        return {
            'direction': '做空',
            'win_rate': win_rate,
            'confidence': confidence,
            'entry_zone': (round(entry_low), round(entry_high)),
            'stop_loss': stop_losses,
            'take_profit': take_profits,
            'reason': '，'.join(reasons),
            'current_price': current_price,
            'nearby_prz': nearby_prz,
        }
    
    def _generate_summary(self, long_plan, short_plan, breakout, trend_scan):
        """產生總結建議"""
        long_wr = long_plan['win_rate']
        short_wr = short_plan['win_rate']
        
        # 判斷推薦方向
        if long_wr - short_wr >= 10:
            recommended = '逢低做多'
            emoji = '🟢'
        elif short_wr - long_wr >= 10:
            recommended = '逢高做空'
            emoji = '🔴'
        else:
            recommended = '區間操作 / 觀望'
            emoji = '🟡'
        
        # 突破覆蓋
        if breakout.get('break_upper'):
            recommended = '強勢突破追多'
            emoji = '🚀'
        elif breakout.get('break_lower'):
            recommended = '破底追空'
            emoji = '💥'
        
        reasons = []
        if trend_scan['overall'] != '中性':
            reasons.append(f"綜合趨勢 {trend_scan['overall']}")
        reasons.append(f"做多勝率 {long_wr:.0f}% vs 做空勝率 {short_wr:.0f}%")
        reasons.append(breakout.get('detail', ''))
        
        return {
            'recommended': recommended,
            'emoji': emoji,
            'reasons': [r for r in reasons if r],
        }


# ═══════════════════════════════════════════════════════════════════
#  6. 輸出格式化
# ═══════════════════════════════════════════════════════════════════

def print_header(current_price, timestamp):
    """印出報告標題"""
    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw)
    
    print()
    print("=" * 68)
    print("       🏛️  PRZ V2 台指期整合分析系統  🏛️")
    print("=" * 68)
    print(f"  ⏰ 分析時間: {now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")
    if timestamp is not None:
        ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(timestamp, 'strftime') else str(timestamp)
        print(f"  📡 資料時間: {ts_str}")
    print(f"  📊 即時點位: {current_price:,.0f} 點")


def print_box_zone(box_info, breakout_info):
    """印出箱體區間定位"""
    loc = box_info['location']
    print(f"  📐 所在箱體: {loc['box_name']} ({loc['box_range'][0]:,.1f} ~ {loc['box_range'][1]:,.1f}) — {loc['position_desc']}")
    print(f"  🎯 箱內位置: {loc['position_pct']*100:.1f}% (0%=下緣, 100%=上緣)")
    if breakout_info.get('break_upper') or breakout_info.get('break_lower') or \
       breakout_info.get('break_waterline_up') or breakout_info.get('break_waterline_down'):
        print(f"  {breakout_info['detail']}")
    print("=" * 68)


def print_trend_scan(trend_results, indicator_results):
    """印出多時間框架趨勢掃描"""
    print()
    print("━" * 68)
    print("  📈 多時間框架 K 線趨勢掃描")
    print("━" * 68)
    
    for tf in ['1', '5', '15', '30']:
        tf_name = TF_DISPLAY.get(tf, tf)
        tf_data = trend_results['timeframes'].get(tf, {})
        trend = tf_data.get('trend', '中性')
        emoji = TREND_EMOJI.get(trend, '⚪')
        
        ind = indicator_results.get(tf, {})
        rsi = ind.get('rsi')
        rsi_str = f"RSI(14): {rsi:.2f}" if rsi is not None else "RSI: N/A"
        vol = ind.get('volume', {})
        vol_str = vol.get('status', '無資料')
        
        print(f"  {tf_name:>5s}:  {emoji} {trend:<4s}  | {rsi_str:<18s} | 量: {vol_str}")
    
    overall = trend_results['overall']
    overall_emoji = TREND_EMOJI.get(overall, '⚪')
    print(f"\n  🔰 綜合趨勢研判: {overall_emoji} {overall} (多方得分: {trend_results['bull_score']} / 空方得分: {trend_results['bear_score']})")


def print_prz_section(current_price, nearby_prz):
    """印出 PRZ 潛在反轉區"""
    print()
    print("━" * 68)
    print("  🎯 PRZ 潛在反轉區 (上方壓力 / 下方支撐)")
    print("━" * 68)
    
    # 上方壓力
    above = nearby_prz.get('above', [])
    print(f"\n  📍 上方壓力 (距 {current_price:,.0f} 上方):")
    if above:
        for i, lvl in enumerate(above, 1):
            dist = lvl['price'] - current_price
            dist_pct = (dist / current_price) * 100
            icon = "⭐" if lvl.get('is_resonance') else "📍"
            count = len(lvl.get('combo_details', []))
            combos = ' | '.join(lvl.get('combo_details', [])[:3])
            tag = f"🔥共振 {count}組" if count > 1 else "單一組合"
            print(f"     {icon} R{i}: {lvl['price']:>10,.0f}  "
                  f"(+{dist:>6,.0f} 點 / +{dist_pct:.2f}%)  "
                  f"[{tag}: {combos}]")
    else:
        print("     (無上方 PRZ)")
    
    # 下方支撐
    below = nearby_prz.get('below', [])
    print(f"\n  📍 下方支撐 (距 {current_price:,.0f} 下方):")
    if below:
        for i, lvl in enumerate(below, 1):
            dist = current_price - lvl['price']
            dist_pct = (dist / current_price) * 100
            icon = "⭐" if lvl.get('is_resonance') else "📍"
            count = len(lvl.get('combo_details', []))
            combos = ' | '.join(lvl.get('combo_details', [])[:3])
            tag = f"🔥共振 {count}組" if count > 1 else "單一組合"
            print(f"     {icon} S{i}: {lvl['price']:>10,.0f}  "
                  f"(-{dist:>6,.0f} 點 / -{dist_pct:.2f}%)  "
                  f"[{tag}: {combos}]")
    else:
        print("     (無下方 PRZ)")


def print_plan(plan, label, color_emoji):
    """印出單一方向的交易計畫"""
    print()
    print("━" * 68)
    wr = plan['win_rate']
    conf = plan['confidence']
    print(f"  {color_emoji} {label} (推估勝率: {wr:.0f}%)")
    print("━" * 68)
    print(f"  📌 信心水準: {conf}")
    
    entry = plan.get('entry_zone')
    if entry:
        print(f"  📌 建議進場: {entry[0]:,.0f} ~ {entry[1]:,.0f}")
    
    # 持倉資訊
    if 'cost' in plan:
        pnl = plan['pnl']
        pnl_emoji = '🟢' if pnl >= 0 else '🔴'
        print(f"  💰 持倉成本: {plan['cost']:,.0f} | {pnl_emoji} 浮動損益: {pnl:+,.0f} 點")
    
    # 停損
    sl_list = plan.get('stop_loss', [])
    if sl_list:
        print(f"  🛑 停損:")
        for sl in sl_list:
            pct_str = f"{sl.get('pct', 0.0):.2f}%"
            print(f"     [{sl['label']}] {sl['price']:,.0f}  (振幅: {sl['distance']:,.0f} 點 / {pct_str})")
    
    # 停利
    tp_list = plan.get('take_profit', [])
    if tp_list:
        print(f"  🎯 停利:")
        for tp in tp_list:
            pct_str = f"{tp.get('pct', 0.0):.2f}%"
            print(f"     [{tp['label']}] {tp['price']:,.0f}  (振幅: {tp['distance']:,.0f} 點 / {pct_str})")
    
    # 印出上下各三個 PRZ
    nearby = plan.get('nearby_prz', {})
    if nearby:
        current_price = plan.get('current_price', 0)
        print(f"\n  🎯 關鍵 PRZ 點位參考 (一般與進階):")
        
        above = nearby.get('above', [])
        for i, lvl in enumerate(reversed(above[:3])):
            dist = lvl['price'] - current_price
            dist_pct = (dist / current_price) * 100 if current_price else 0
            is_adv = lvl.get('is_resonance')
            cat = "【進階】" if is_adv else "【一般】"
            icon = "⭐" if is_adv else "📍"
            print(f"     {icon} 壓力 {cat}: {lvl['price']:,.0f} (+{dist:,.0f}點 / +{dist_pct:.2f}%)")
            
        below = nearby.get('below', [])
        for i, lvl in enumerate(below[:3]):
            dist = current_price - lvl['price']
            dist_pct = (dist / current_price) * 100 if current_price else 0
            is_adv = lvl.get('is_resonance')
            cat = "【進階】" if is_adv else "【一般】"
            icon = "⭐" if is_adv else "📍"
            print(f"     {icon} 支撐 {cat}: {lvl['price']:,.0f} (-{dist:,.0f}點 / -{dist_pct:.2f}%)")
    
    # 理由
    print(f"  💡 理由: {plan.get('reason', '-')}")


def print_summary(summary, breakout):
    """印出總結建議"""
    print()
    print("━" * 68)
    print("  💡 總結建議")
    print("━" * 68)
    print(f"  {summary['emoji']} 推薦方向: {summary['recommended']}")
    for r in summary.get('reasons', []):
        print(f"     • {r}")
    print(f"  ⚠️ 5分K 連3根突破觀察: {breakout.get('detail', '尚未觸發')}")
    print("=" * 68)


# ═══════════════════════════════════════════════════════════════════
#  7. 主流程
# ═══════════════════════════════════════════════════════════════════

def run_analysis(price_override=None, position=None, cost=None):
    """
    執行完整 PRZ V2 分析。
    
    Args:
        price_override: 指定點位（None 則自動抓取即時價）
        position: 'long' / 'short' / None
        cost: 持倉成本價（僅 position 非 None 時使用）
    """
    # ─── 初始化引擎 ───
    box_engine = BoxZoneEngine()
    trend_scanner = MultiTFTrendScanner()
    indicator_engine = IndicatorEngine()
    prz_engine = PRZMatrixEngine()
    advisor = SmartAdvisor()
    
    # ─── 步驟 1: 抓取即時價格 ───
    if price_override is not None:
        current_price = float(price_override)
        timestamp = None
        print(f"\n  📌 使用指定點位: {current_price:,.0f}")
    else:
        print("\n  📡 正在抓取即時行情...")
        current_price, timestamp = get_current_price()
        if current_price is None:
            print("  ❌ 無法取得即時行情，請確認網路或使用 --price 指定點位")
            return
    
    # ─── 步驟 2: 抓取多時間框架 K 線 ───
    print("  📡 正在抓取多時間框架 K 線資料...")
    all_data = fetch_all_timeframes_v2()
    
    # ─── 步驟 3: 箱體定位與勝率 ───
    # 先做趨勢掃描以取得 trend_bias
    trend_results = trend_scanner.scan(all_data)
    box_win_rates = box_engine.estimate_win_rate(current_price, trend_results['trend_bias'])
    
    # ─── 步驟 4: 5 分 K 突破檢測 ───
    df_5min = all_data.get('5', pd.DataFrame())
    breakout = box_engine.check_5min_breakout(df_5min)
    
    # ─── 步驟 5: RSI 與成交量指標 ───
    indicators = indicator_engine.scan_all(all_data)
    
    # ─── 步驟 6: PRZ 矩陣計算 ───
    prz_result = prz_engine.calculate(all_data, trend_results, current_price)
    
    # ─── 步驟 7: 輸出報告 ───
    print_header(current_price, timestamp)
    print_box_zone(box_win_rates, breakout)
    print_trend_scan(trend_results, indicators)
    print_prz_section(current_price, prz_result['nearby'])
    
    # ─── 步驟 8: 產生交易建議 ───
    if position:
        # 持倉模式
        pos_advice = advisor.generate_position_advice(
            current_price, prz_result['nearby'], indicators,
            box_win_rates, breakout, trend_results,
            position, cost or current_price
        )
        plan = pos_advice['position']
        color = '🟢' if pos_advice['type'] == '多單' else '🔴'
        print_plan(plan, f"{pos_advice['type']} 持倉建議", color)
    else:
        # 空手模式 — 同時輸出做多與做空
        advice = advisor.generate_both_sides(
            current_price, prz_result['nearby'], indicators,
            box_win_rates, breakout, trend_results
        )
        print_plan(advice['long'], '做多方案', '🟢')
        print_plan(advice['short'], '做空方案', '🔴')
        print_summary(advice['summary'], breakout)
    
    return {
        'price': current_price,
        'box': box_win_rates,
        'trend': trend_results,
        'indicators': indicators,
        'prz': prz_result,
        'breakout': breakout,
        'advice': pos_advice if position else advice
    }


# ═══════════════════════════════════════════════════════════════════
#  CLI 入口
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='🏛️ PRZ V2 台指期整合分析系統',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  python prz_v2_analyzer.py                            # 空手查詢
  python prz_v2_analyzer.py --price 44245              # 指定點位查詢
  python prz_v2_analyzer.py --position long --cost 42711   # 持有多單
  python prz_v2_analyzer.py --position short --cost 43886  # 持有空單
        """
    )
    parser.add_argument('--price', type=float, default=None,
                        help='指定分析點位 (不填則自動抓取即時價格)')
    parser.add_argument('--position', choices=['long', 'short'], default=None,
                        help='持倉方向: long=多單, short=空單')
    parser.add_argument('--cost', type=float, default=None,
                        help='持倉成本價')
    
    args = parser.parse_args()
    
    if args.position and not args.cost:
        print("⚠️ 使用 --position 時請同時指定 --cost (持倉成本價)")
        return
    
    run_analysis(
        price_override=args.price,
        position=args.position,
        cost=args.cost,
    )


if __name__ == '__main__':
    main()
