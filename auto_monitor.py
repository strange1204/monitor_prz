"""
台指期 PRZ 每分鐘即時監控與高信心水準 Email 觸發通報系統
=====================================================
1. 每分鐘自動抓取台指期 1分K / 5分K / 15分K / 日K 最新數據
2. 採用【Mode 3 雙演算法優點融合模式】計算 PRZ 超級共振與交易建議
3. 當發現【信心水準：高】且與【前一次發送之通知內容不同】時，自動觸發 Gmail Email 寄送
4. 避免重複垃圾郵件干擾，並持續於終端機印出即時監控日誌
"""

import sys
import os
import time
import json
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')

# 匯入 PRZ 分析模組
from data_fetcher import get_current_price, fetch_all_timeframes
from hybrid_swing_detector import get_hybrid_swings
from prz_calculator import calculate_multi_timeframe_prz, group_prz_levels, get_grouped_nearby_prz
from trade_advisor import determine_trend, generate_full_advice
from notifier import send_email_report
from box_swing_detector import DAILY_MASTER_HIGH, DAILY_MASTER_LOW

STATE_FILE = "C:\\monitor_PRZ\\last_notification_state.json"

def load_last_state():
    """載入前一次發送 Email 通知的狀態"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_last_state(state):
    """儲存本次發送 Email 通知的狀態"""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 儲存通知狀態失敗: {e}")

def build_email_template(current_price, nearby_prz, advice):
    """使用經典行情與盤態樣板構建 Email 內文"""
    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw)
    
    trend = advice.get('trend', {})
    overall_trend = trend.get('overall_trend', '中性')
    daily_macro = trend.get('daily_macro', '中性')
    entry = advice.get('entry', {})
    
    lines = []
    lines.append("親愛的 Brian 您好：\n")
    lines.append("🚨【台指期 PRZ 高信心水準交易警報】🚨")
    lines.append("==========================================")
    lines.append(f"⏰ 分析時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")
    lines.append(f"📊 台指期即時點位：{current_price:,.0f} 點")
    lines.append("==========================================\n")
    
    lines.append(f"🏛️ 日線大方向：{daily_macro}")
    lines.append(f"🔰 綜合趨勢研判：{overall_trend}")
    lines.append(f"📌 進場建議：{entry.get('direction', '觀望')}")
    if entry.get('entry_zone'):
        lines.append(f"   建議進場區間：{entry['entry_zone'][0]:,.0f} ~ {entry['entry_zone'][1]:,.0f}")
    lines.append(f"⭐ 信心水準：{entry.get('confidence', '高')} (🔥高信心水準觸發)")
    lines.append(f"💡 判斷理由：{entry.get('reason', '-')}\n")
    
    sl_list = advice.get('stop_loss', [])
    if sl_list:
        lines.append("🛑 建議停損點位 (Stop Loss)：")
        for sl in sl_list:
            lines.append(f"   - [{sl['label']}停損] {sl['price']:,.0f} 點 (距離當前: {sl['distance']:,.0f} 點)")
        lines.append("")
        
    tp_list = advice.get('take_profit', [])
    if tp_list:
        lines.append("🎯 建議停利點位 (Take Profit)：")
        for tp in tp_list:
            lines.append(f"   - [{tp['label']}停利] {tp['price']:,.0f} 點 (距離當前: {tp['distance']:,.0f} 點)")
        lines.append("")
        
    lines.append("📍 附近 Key PRZ 價位 (雙模型超級共振與去重結果)：")
    lines.append("  【上方壓力 PRZ】:")
    for lvl in nearby_prz.get('above', [])[:3]:
        combos = " | ".join(lvl.get('combo_details', []))
        count = len(lvl.get('combo_details', []))
        tag = f"🔥超級共振 {count}組" if count > 1 else "單一組合"
        lines.append(f"   - {lvl['price']:,.0f} 點 (+{lvl['price'] - current_price:,.0f} 點) [{tag}: {combos}]")
        
    lines.append("\n  【下方支撐 PRZ】:")
    for lvl in nearby_prz.get('below', [])[:3]:
        combos = " | ".join(lvl.get('combo_details', []))
        count = len(lvl.get('combo_details', []))
        tag = f"🔥超級共振 {count}組" if count > 1 else "單一組合"
        lines.append(f"   - {lvl['price']:,.0f} 點 (-{current_price - lvl['price']:,.0f} 點) [{tag}: {combos}]")
        
    lines.append("\n==========================================")
    lines.append("系統提示: 本郵件由 C:\\monitor_PRZ\\auto_monitor.py 自動監控系統觸發發送。")
    return "\n".join(lines)

def run_single_check():
    """執行一次即時監控檢查"""
    tz_tw = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
    
    current_price, latest_ts = get_current_price()
    if current_price is None:
        print(f"[{now_str}] ⚠️ 無法取得即時價格，將於下一分鐘重試...")
        return
        
    all_data = fetch_all_timeframes()
    all_swings = get_hybrid_swings(all_data)
    
    tf_pairs = {'5': None, '1': None}
    if '5' in all_swings and not all_swings['5']['highs'].empty and not all_swings['5']['lows'].empty:
        tf_pairs['5分K'] = (all_swings['5']['highs']['price'].max(), all_swings['5']['lows']['price'].min())
    if '1' in all_swings and not all_swings['1']['highs'].empty and not all_swings['1']['lows'].empty:
        tf_pairs['1分K'] = (all_swings['1']['highs']['price'].max(), all_swings['1']['lows']['price'].min())
        
    tf_pairs['日線權威箱體'] = (DAILY_MASTER_HIGH, DAILY_MASTER_LOW)
    
    # 移除 None key
    tf_pairs = {k: v for k, v in tf_pairs.items() if v is not None}
    
    all_prz = calculate_multi_timeframe_prz(tf_pairs)
    grouped_prz = group_prz_levels(all_prz, tolerance_points=3.0)
    nearby_prz = get_grouped_nearby_prz(current_price, grouped_prz, n_min=3)
    
    trend_swings = {}
    tf_map = {'D': 'daily', '15': '15min', '5': '5min', '1': '1min'}
    for tf, swings in all_swings.items():
        highs = swings.get('highs', None)
        lows = swings.get('lows', None)
        combined = []
        if highs is not None and not highs.empty:
            for _, row in highs.iterrows():
                combined.append({'type': 'high', 'price': row['price'], 'bar_index': row['bar_index']})
        if lows is not None and not lows.empty:
            for _, row in lows.iterrows():
                combined.append({'type': 'low', 'price': row['price'], 'bar_index': row['bar_index']})
        combined.sort(key=lambda x: x['bar_index'])
        trend_swings[tf_map.get(tf, tf)] = combined
        
    trend_info = determine_trend(trend_swings)
    
    flat_prz = []
    for g in grouped_prz:
        combos_str = " / ".join(g.get('combo_details', []))
        flat_prz.append({
            'price': g['price'],
            'type': 'support' if g['price'] < current_price else 'resistance',
            'name': combos_str,
            'is_resonance': g.get('is_resonance', False)
        })
        
    advisor_nearby = {
        'support': [lvl for lvl in flat_prz if lvl['type'] == 'support'],
        'resistance': [lvl for lvl in flat_prz if lvl['type'] == 'resistance']
    }
    advisor_nearby['support'].sort(key=lambda x: x['price'], reverse=True)
    advisor_nearby['resistance'].sort(key=lambda x: x['price'])
    
    advice = generate_full_advice(
        current_price=current_price,
        nearby_prz=advisor_nearby,
        trend_info=trend_info,
        prz_levels=flat_prz,
        has_position=None
    )
    
    entry = advice.get('entry', {})
    confidence = entry.get('confidence', '低')
    direction = entry.get('direction', '觀望')
    reason = entry.get('reason', '')
    
    print(f"[{now_str}] 📊 當前點位: {current_price:,.0f} | 方向: {direction} | 信心水準: {confidence}")
    
    # 檢查觸發條件
    if confidence == '高':
        # 建立目前狀態特徵碼 (方向 + 建議進場位 + 原因)
        current_signal_key = {
            'direction': direction,
            'entry_zone': entry.get('entry_zone'),
            'reason': reason,
            'price': round(current_price)
        }
        
        last_state = load_last_state()
        last_key = last_state.get('signal_key', {})
        
        # 比較是否與前次不同
        if current_signal_key != last_key:
            print(f"[{now_str}] 🚨 發現【信心水準：高】新訊號！正在發送 Email 通知...")
            
            subject = f"【台指期 PRZ 警報】當前點位 {current_price:,.0f} 點 - 建議 {direction} (信心水準: 高)"
            email_body = build_email_template(current_price, nearby_prz, advice)
            
            success = send_email_report(subject, email_body)
            if success:
                print(f"[{now_str}] ✅ Email 成功送達！已更新前次通知狀態。")
                save_last_state({
                    'timestamp': now_str,
                    'price': current_price,
                    'signal_key': current_signal_key
                })
        else:
            print(f"[{now_str}] ℹ️ 偵測到高信心水準訊號，但與前次通知內容相同，跳過重複發送。")


def start_monitoring_loop(interval_seconds=60):
    print("=" * 65)
    print("  📡 台指期 PRZ 每分鐘即時監控服務已啟動...")
    print("  ⭐ 觸發條件: 信心水準 == '高' 且與前次通知內容不同")
    print(f"  ⏰ 檢查間隔: 每 {interval_seconds} 秒")
    print("=" * 65)
    
    while True:
        try:
            run_single_check()
        except Exception as e:
            print(f"⚠️ 監控過程發生異常: {e}")
        
        time.sleep(interval_seconds)

if __name__ == '__main__':
    start_monitoring_loop(60)
