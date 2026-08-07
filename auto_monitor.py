"""
台指期 PRZ V2 每分鐘即時監控與高信心水準 Email 觸發通報系統
=====================================================
1. 僅在台指期交易時間段內執行每分鐘監控與分析。
2. 採用 PRZ V2 整合分析引擎 (prz_v2_analyzer) 進行分析。
3. 當發現【做多或做空方案的信心水準為高】且與【前一次發送之通知內容不同】時，自動發送 Email 警報。
4. 在每天交易結束時檢查並通報三大法人現貨買賣超數據。
"""

import sys
import os
import time
import json
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')

# 匯入 PRZ V2 模組
from prz_v2_analyzer import run_analysis
from notifier import send_email_report
from check_fini_and_notify import check_and_notify_fini

STATE_FILE = "C:\\monitor_PRZ\\last_notification_state.json"

def is_trading_hours():
    """
    判定目前是否在台指期交易時間段內 (包含日盤與夜盤，排除週末休市)
    - 日盤: 週一至週五 08:45 - 13:45
    - 夜盤: 週一至週五 15:00 - 隔天 05:00 (週五夜盤交易至週六 05:00 結束)
    """
    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw)
    weekday = now.weekday()  # 0 = Monday, ..., 6 = Sunday
    hour = now.hour
    minute = now.minute

    # 週末休市 (週六 05:00 後至週日全天)
    if weekday == 5:  # Saturday
        # 週六凌晨 5 點前算週五夜盤的尾聲
        if hour < 5:
            return True
        return False
    elif weekday == 6:  # Sunday
        return False
        
    # 週一開盤前的冷卻時段 (週一凌晨至 08:45 前不開盤)
    elif weekday == 0:
        if hour < 8 or (hour == 8 and minute < 45):
            return False

    # 平日開盤時段判定
    # 1. 日盤 (08:45 - 13:45)
    if (hour == 8 and minute >= 45) or (9 <= hour < 13) or (hour == 13 and minute <= 45):
        return True
        
    # 2. 夜盤 (15:00 - 05:00 隔天)
    if hour >= 15 or hour < 5:
        return True

    return False

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

def build_email_template_v2(price, box_wr, trend_results, indicators, breakout, prz_result, advice):
    """建立 V2 格式的美化 Email 內容"""
    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw)
    
    loc = box_wr['location']
    
    lines = []
    lines.append("親愛的 Brian 您好：\n")
    lines.append("🚨【台指期 PRZ V2 整合分析交易警報】🚨")
    lines.append("==========================================")
    lines.append(f"⏰ 分析時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")
    lines.append(f"📊 即時點位：{price:,.0f} 點")
    lines.append(f"📐 所在箱體：{loc['box_name']} ({loc['box_range'][0]:,.0f} ~ {loc['box_range'][1]:,.0f})")
    lines.append(f"🎯 箱內位置：{loc['position_pct']*100:.1f}% (0%=下緣, 100%=上緣)")
    if breakout.get('detail') and breakout.get('detail') != '尚未觸發':
        lines.append(f"⚠️ 突破偵測：{breakout['detail']}")
    lines.append("==========================================\n")
    
    # 趨勢
    overall = trend_results['overall']
    lines.append(f"🔰 綜合趨勢研判：{overall} (多方得分: {trend_results['bull_score']} / 空方得分: {trend_results['bear_score']})")
    
    # 做多方案
    long_plan = advice['long']
    lines.append(f"\n🟢 做多方案 (推估勝率: {long_plan['win_rate']:.0f}%)")
    lines.append(f"   • 信心水準：{long_plan['confidence']}")
    lines.append(f"   • 建議進場：{long_plan['entry_zone'][0]:,.0f} ~ {long_plan['entry_zone'][1]:,.0f}")
    lines.append("   • 停損點位：")
    for sl in long_plan['stop_loss']:
        lines.append(f"     - [{sl['label']}] {sl['price']:,.0f} (振幅: {sl['distance']}點 / {sl['pct']}%)")
    lines.append("   • 停利點位：")
    for tp in long_plan['take_profit']:
        lines.append(f"     - [{tp['label']}] {tp['price']:,.0f} (振幅: {tp['distance']}點 / {tp['pct']}%)")
    lines.append(f"   • 做多理由：{long_plan['reason']}")
    
    # 做空方案
    short_plan = advice['short']
    lines.append(f"\n🔴 做空方案 (推估勝率: {short_plan['win_rate']:.0f}%)")
    lines.append(f"   • 信心水準：{short_plan['confidence']}")
    lines.append(f"   • 建議進場：{short_plan['entry_zone'][0]:,.0f} ~ {short_plan['entry_zone'][1]:,.0f}")
    lines.append("   • 停損點位：")
    for sl in short_plan['stop_loss']:
        lines.append(f"     - [{sl['label']}] {sl['price']:,.0f} (振幅: {sl['distance']}點 / {sl['pct']}%)")
    lines.append("   • 停利點位：")
    for tp in short_plan['take_profit']:
        lines.append(f"     - [{tp['label']}] {tp['price']:,.0f} (振幅: {tp['distance']}點 / {tp['pct']}%)")
    lines.append(f"   • 做空理由：{short_plan['reason']}")
    
    # 總結
    summary = advice['summary']
    lines.append(f"\n💡 推薦方向：{summary['recommended']}")
    for r in summary.get('reasons', []):
        lines.append(f"   • {r}")
        
    lines.append("\n🎯 關鍵 PRZ 點位參考 (一般與進階):")
    above = prz_result['nearby'].get('above', [])
    for lvl in reversed(above[:3]):
        dist = lvl['price'] - price
        dist_pct = (dist / price) * 100
        is_adv = lvl.get('is_resonance')
        cat = "【進階】" if is_adv else "【一般】"
        lines.append(f"   - 壓力 {cat}: {lvl['price']:,.0f} (+{dist:.0f}點 / +{dist_pct:.2f}%)")
        
    below = prz_result['nearby'].get('below', [])
    for lvl in below[:3]:
        dist = price - lvl['price']
        dist_pct = (dist / price) * 100
        is_adv = lvl.get('is_resonance')
        cat = "【進階】" if is_adv else "【一般】"
        lines.append(f"   - 支撐 {cat}: {lvl['price']:,.0f} (-{dist:.0f}點 / -{dist_pct:.2f}%)")
        
    lines.append("\n==========================================")
    lines.append("系統提示: 本郵件由 C:\\monitor_PRZ\\auto_monitor.py 自動監控系統觸發發送。")
    return "\n".join(lines)

def run_single_check():
    """執行單次即時監控檢查"""
    tz_tw = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. 檢查是否在交易時段內
    if not is_trading_hours():
        print(f"[{now_str}] 💤 非交易時段 (週末休市，或每日收盤冷卻期)，跳過分析監控。")
        # 即使非開盤期間，仍進行外資三大法人盤後現貨通報檢查
        try:
            check_and_notify_fini()
        except Exception as e:
            print(f"  ⚠️ 外資現貨數據檢查異常: {e}")
        return

    # 2. 進行 PRZ V2 核心分析
    try:
        analysis = run_analysis()
        if not analysis or 'advice' not in analysis:
            print(f"[{now_str}] ⚠️ V2 分析模組未回傳有效建議。")
            return
            
        current_price = analysis['price']
        box_wr = analysis['box']
        trend_results = analysis['trend']
        indicators = analysis['indicators']
        breakout = analysis['breakout']
        prz_result = analysis['prz']
        advice = analysis['advice']
        
        long_plan = advice['long']
        short_plan = advice['short']
        summary = advice['summary']
        
        # 3. 判斷是否有高信心水準信號，並比對狀態防止重複發送
        has_high_confidence = (long_plan['confidence'] == '🔥高' or short_plan['confidence'] == '🔥高')
        
        if has_high_confidence:
            # 建立目前狀態特徵碼 (避免加入變動劇烈的 price，防止洗信)
            current_signal_key = {
                'recommended': summary['recommended'],
                'long_confidence': long_plan['confidence'],
                'short_confidence': short_plan['confidence'],
                'long_entry': long_plan['entry_zone'],
                'short_entry': short_plan['entry_zone']
            }
            
            last_state = load_last_state()
            last_key = last_state.get('signal_key', {})
            
            # 比較是否與前一次發送的訊號不同
            if current_signal_key != last_key:
                print(f"[{now_str}] 🚨 發現【信心水準：高】新訊號！正在發送 Email 通知...")
                
                subject = f"【PRZ V2 警報】建議 {summary['recommended']} (多空雙方案與關鍵PRZ分析)"
                email_body = build_email_template_v2(
                    current_price, box_wr, trend_results, indicators, breakout, prz_result, advice
                )
                
                success = send_email_report(subject, email_body)
                if success:
                    print(f"[{now_str}] ✅ Email 成功送達！已更新前次通知狀態。")
                    save_last_state({
                        'timestamp': now_str,
                        'price': current_price,
                        'signal_key': current_signal_key,
                        'fini_notified_date': last_state.get('fini_notified_date') # 保留外資通報狀態
                    })
            else:
                print(f"[{now_str}] ℹ️ 偵測到高信心水準訊號，但與前次通知內容相同，跳過發送。")
        else:
            print(f"[{now_str}] 📊 監控中，當前做多勝率 {long_plan['win_rate']:.0f}% (信心:{long_plan['confidence']})，做空勝率 {short_plan['win_rate']:.0f}% (信心:{short_plan['confidence']})。")
            
    except Exception as e:
        print(f"[{now_str}] ❌ 執行即時監控分析失敗: {e}")
        import traceback
        traceback.print_exc()

    # 4. 外資現貨買賣超數據檢查
    try:
        check_and_notify_fini()
    except Exception as e:
        print(f"  ⚠️ 外資現貨數據檢查異常: {e}")

def start_monitoring_loop(interval_seconds=60):
    print("=" * 65)
    print("  📡 台指期 PRZ V2 每分鐘即時監控服務已啟動...")
    print("  ⭐ 觸發條件: 做多或做空之信心水準 == '高' 且與前次通知內容不同")
    print(f"  ⏰ 檢查間隔: 每 {interval_seconds} 秒")
    print("=" * 65)
    
    while True:
        try:
            run_single_check()
        except Exception as e:
            print(f"⚠️ 監控循環異常: {e}")
        time.sleep(interval_seconds)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='台指期 PRZ V2 自動監控服務')
    parser.add_argument('--single-run', '-s', action='store_true', help='僅執行一次監控檢查 (適合排程)')
    parser.add_argument('--interval', '-i', type=int, default=60, help='監控檢查間隔秒數 (預設 60 秒)')
    args = parser.parse_args()
    
    if args.single_run:
        run_single_check()
    else:
        start_monitoring_loop(args.interval)

if __name__ == '__main__':
    main()
