"""
台指期 PRZ 諧波交易分析系統 - 主程式 (C:\\monitor_PRZ)
=====================================================
功能特點:
 1. 支援日K, 15分K, 5分K, 1分K 多時間框架分析
 2. 基於 Scott Carney 5-Bar Fractal Rule 尋找 Swing High/Low
 3. 計算 PRZ 潛在反轉區（0.236~1.618 全黃金比率）與共振判定
 4. 提供近端 PRZ 壓力與支撐價位
 5. 提供多單/空單建議，並至少提供各 3 個停損點與 3 個停利點
 6. 支援互動選單模式 (Interactive Mode)
 7. 支援 Gmail SMTP Email 即時分析發信與警報
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')

# 匯入自訂模組
from data_fetcher import fetch_kline, get_current_price, fetch_all_timeframes
from swing_detector import detect_swings, find_major_swings, get_multi_timeframe_swings
from prz_calculator import (
    calculate_prz_levels,
    calculate_multi_timeframe_prz,
    find_resonance_zones,
    get_nearby_prz,
    format_prz_report
)
from trade_advisor import (
    determine_trend,
    generate_full_advice,
    format_advice_report
)
from notifier import send_email_report

TF_NAMES = {
    'D': '日K',
    '15': '15分K',
    '5': '5分K',
    '1': '1分K'
}

def print_header(current_price, timestamp):
    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw)
    
    print("=" * 65)
    print("       🏛️  台指期 PRZ 諧波交易分析系統  🏛️")
    print("       基於 Scott M. Carney 諧波交易理論")
    print("=" * 65)
    print(f"  ⏰ 分析時間: {now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")
    
    if timestamp is not None:
        ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(timestamp, 'strftime') else str(timestamp)
        print(f"  📡 資料時間: {ts_str}")
    
    print(f"  📊 台指期即時點位: {current_price:,.0f}")
    print("=" * 65)


def print_swing_section(all_swings, all_data):
    print()
    print("━" * 65)
    print("  📐 多時間框架 Swing 轉折點（含日線大方向 5-Bar Fractal 偵測）")
    print("━" * 65)
    
    for tf in ['D', '15', '5', '1']:
        if tf not in all_swings:
            continue
        
        swings = all_swings[tf]
        highs = swings.get('highs', None)
        lows = swings.get('lows', None)
        
        tf_name = TF_NAMES.get(tf, tf)
        print(f"\n  🔹 {tf_name} 級別:")
        
        if highs is not None and not highs.empty:
            recent_highs = highs.sort_values('bar_index', ascending=False).head(5)
            prices_str = " | ".join([f"{h['price']:,.0f}" for _, h in recent_highs.iterrows()])
            print(f"     上點 (Swing High): {prices_str}")
            
            if tf == 'D':
                recent_window_highs = highs.sort_values('bar_index', ascending=False).head(10)
                master_high = recent_window_highs.loc[recent_window_highs['price'].idxmax()]
            else:
                master_high = highs.loc[highs['price'].idxmax()]
                
            ts_h = master_high['timestamp']
            ts_h_str = ts_h.strftime('%m/%d') if tf == 'D' else (ts_h.strftime('%m/%d %H:%M') if hasattr(ts_h, 'strftime') else str(ts_h)[:16])
            print(f"     主上點 (Master High): {master_high['price']:,.0f} ({ts_h_str})")
        else:
            print(f"     上點: 未偵測到合格 Swing High")
        
        if lows is not None and not lows.empty:
            recent_lows = lows.sort_values('bar_index', ascending=False).head(5)
            prices_str = " | ".join([f"{l['price']:,.0f}" for _, l in recent_lows.iterrows()])
            print(f"     下點 (Swing Low):  {prices_str}")
            
            if tf == 'D':
                recent_window_lows = lows.sort_values('bar_index', ascending=False).head(10)
                master_low = recent_window_lows.loc[recent_window_lows['price'].idxmin()]
            else:
                master_low = lows.loc[lows['price'].idxmin()]
                
            ts_l = master_low['timestamp']
            ts_l_str = ts_l.strftime('%m/%d') if tf == 'D' else (ts_l.strftime('%m/%d %H:%M') if hasattr(ts_l, 'strftime') else str(ts_l)[:16])
            print(f"     主下點 (Master Low):  {master_low['price']:,.0f} ({ts_l_str})")
        else:
            print(f"     下點: 未偵測到合格 Swing Low")
        
        if tf == 'D' and highs is not None and lows is not None and not highs.empty and not lows.empty:
            delta_h = master_high['price'] - master_low['price']
            print(f"     日K波段箱體高度 ΔH: {delta_h:,.0f} 點 ({master_high['price']:,.0f} ~ {master_low['price']:,.0f})")


def build_multi_tf_swing_pairs(all_swings, target_tfs=['5', '1']):
    """
    從指定的時間框架（依需求：僅採用 5分K 與 1分K）提取最顯著的 (swing_high, swing_low) 對用以計算 PRZ。
    """
    pairs = {}
    for tf in target_tfs:
        if tf not in all_swings:
            continue
        swings = all_swings[tf]
        highs = swings.get('highs', None)
        lows = swings.get('lows', None)
        
        if highs is None or lows is None or highs.empty or lows.empty:
            continue
        
        master_high = highs['price'].max()
        master_low = lows['price'].min()
        
        if master_high > master_low:
            tf_name = TF_NAMES.get(tf, tf)
            pairs[tf_name] = (master_high, master_low)
    
    return pairs


def build_trend_swings(all_swings):
    trend_input = {}
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
        tf_key = tf_map.get(tf, tf)
        trend_input[tf_key] = combined
    
    return trend_input


def build_flat_prz_for_advisor(prz_levels):
    flat_levels = []
    for lvl in prz_levels:
        name = lvl.get('name', '')
        if not name and 'combo_details' in lvl and lvl['combo_details']:
            name = " / ".join(lvl['combo_details'])
            
        entry = {
            'price': lvl['price'],
            'ratio': lvl.get('ratio', 0),
            'name': name,
            'source': lvl.get('source', ''),
            'is_resonance': lvl.get('is_resonance', False),
        }
        direction = lvl.get('direction', '')
        if direction in ('support', 'extension_down'):
            entry['type'] = 'support'
        elif direction in ('resistance', 'extension_up'):
            entry['type'] = 'resistance'
        else:
            entry['type'] = 'support'
        
        flat_levels.append(entry)
    
    return flat_levels


def print_prz_section(current_price, prz_levels):
    from prz_calculator import get_grouped_nearby_prz
    nearby = get_grouped_nearby_prz(current_price, prz_levels, n_min=3)
    
    print()
    print("━" * 65)
    print("  🎯 PRZ 潛在反轉區（黃金分割共振點位 - 僅 5分K & 1分K）")
    print("━" * 65)
    
    print(f"\n  📍 上方壓力 PRZ（距當前 {current_price:,.0f} 上方，去重至少 3 個點位）:")
    above = nearby.get('above', [])
    if above:
        for i, lvl in enumerate(above, 1):
            dist = lvl['price'] - current_price
            dist_pct = (dist / current_price) * 100
            icon = "⭐" if lvl.get('is_resonance') else "📍"
            combos_str = " | ".join(lvl.get('combo_details', []))
            count = len(lvl.get('combo_details', []))
            res_tag = f"🔥共振 {count}組組合" if count > 1 else "單一組合"
            
            print(f"     {icon} PRZ {i}: {lvl['price']:>10,.0f}  "
                  f"(+{dist:>6,.0f} 點 / +{dist_pct:.2f}%)  "
                  f"[{res_tag}: {combos_str}]")
    else:
        print("     (無上方 PRZ)")
    
    print(f"\n  📍 下方支撐 PRZ（距當前 {current_price:,.0f} 下方，去重至少 3 個點位）:")
    below = nearby.get('below', [])
    if below:
        for i, lvl in enumerate(below, 1):
            dist = current_price - lvl['price']
            dist_pct = (dist / current_price) * 100
            icon = "⭐" if lvl.get('is_resonance') else "📍"
            combos_str = " | ".join(lvl.get('combo_details', []))
            count = len(lvl.get('combo_details', []))
            res_tag = f"🔥共振 {count}組組合" if count > 1 else "單一組合"
            
            print(f"     {icon} PRZ {i}: {lvl['price']:>10,.0f}  "
                  f"(-{dist:>6,.0f} 點 / -{dist_pct:.2f}%)  "
                  f"[{res_tag}: {combos_str}]")
    else:
        print("     (無下方 PRZ)")
    
    return nearby


def print_trade_advice(advice):
    print()
    print("━" * 65)
    print("  💡 交易與停損停利建議")
    print("━" * 65)
    
    trend = advice.get('trend', {})
    overall = trend.get('overall_trend', '未知')
    trend_emoji = {'偏多': '🟢', '偏空': '🔴', '中性': '🟡'}.get(overall, '⚪')
    
    print(f"\n  🔰 趨勢研判: {trend_emoji} {overall}")
    for tf_key in ['daily', '15min', '5min', '1min']:
        if tf_key in trend:
            emoji = {'偏多': '🟢', '偏空': '🔴', '中性': '🟡'}.get(trend[tf_key], '⚪')
            print(f"     {tf_key}: {emoji} {trend[tf_key]}")
    
    entry = advice.get('entry', {})
    dir_str = entry.get('direction', '觀望')
    dir_emoji = {'做多': '🟢', '做空': '🔴', '觀望': '🟡'}.get(dir_str.split()[0] if dir_str else '觀望', '⚪')
    
    print(f"\n  📌 進場/部位狀態: {dir_emoji} {dir_str}")
    if entry.get('entry_zone'):
        z = entry['entry_zone']
        print(f"     建議進場區間: {z[0]:,.0f} ~ {z[1]:,.0f}")
    print(f"     信心水準: {entry.get('confidence', '-')}")
    print(f"     判斷理由: {entry.get('reason', '-')}")
    
    sl_list = advice.get('stop_loss', [])
    if sl_list:
        print(f"\n  🛑 停損建議（建議至少 3 個位階）:")
        labels = ['①', '②', '③', '④', '⑤']
        for i, sl in enumerate(sl_list):
            label = labels[i] if i < len(labels) else f"({i+1})"
            prz_tag = f" [{sl['prz_name']}]" if sl.get('prz_name') else ""
            print(f"     {label} [{sl['label']}停損]: {sl['price']:>10,.0f}  "
                  f"(距離當前: {sl['distance']:>6,.0f} 點){prz_tag}")
    else:
        print(f"\n  🛑 停損建議: 無部位或目前建議觀望")
    
    tp_list = advice.get('take_profit', [])
    if tp_list:
        print(f"\n  🎯 停利建議（建議至少 3 個位階）:")
        labels = ['①', '②', '③', '④', '⑤']
        for i, tp in enumerate(tp_list):
            label = labels[i] if i < len(labels) else f"({i+1})"
            prz_tag = f" [{tp['prz_name']}]" if tp.get('prz_name') else ""
            print(f"     {label} [{tp['label']}停利]: {tp['price']:>10,.0f}  "
                  f"(距離當前: {tp['distance']:>6,.0f} 點){prz_tag}")
    else:
        print(f"\n  🎯 停利建議: 無部位或目前建議觀望")


def print_prz_theory():
    print()
    print("━" * 65)
    print("  📖 PRZ 黃金分割係數理論依據")
    print("━" * 65)
    print("""
  Φ (黃金比率) = 1.618033...

  ┌─────────┬────────────────────────────────────────────┐
  │  比率   │  名稱 & 數學來源                           │
  ├─────────┼────────────────────────────────────────────┤
  │  0.236  │  淺層回撤 — Φ⁻³                           │
  │  0.382  │  標準回撤 — Φ⁻²                           │
  │  0.500  │  中心回撤 — 對稱中點                      │
  │  0.618  │  深度回撤 — Φ⁻¹                           │
  │  0.786  │  加特利回撤 — √0.618 (Gartley Pattern)    │
  │  0.886  │  蝙蝠極限位 — √0.786 (Bat Pattern)        │
  │  1.130  │  陷阱區 — ⁴√1.618 (假突破/洗盤陷阱)       │
  │  1.272  │  蝴蝶延伸 — √1.618 (Butterfly Pattern)    │
  │  1.618  │  螃蟹延伸 — Φ (Crab Pattern)              │
  └─────────┴────────────────────────────────────────────┘

  📘 權威著作: Scott M. Carney《Harmonic Trading》Vol.1 & Vol.2
  📗 補充著作: Larry Pesavento《Fibonacci Ratios with Pattern Recognition》
  📙 幾何參考: Bryce Gilmore《Geometry of Stock Market Wave Ratios》
  """)


def build_email_body(current_price, nearby_prz, advice):
    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw)
    
    lines = []
    lines.append(f"親愛的 Brian 您好：\n")
    lines.append(f"【台指期 PRZ 諧波交易分析即時報告】")
    lines.append(f"• 分析時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")
    lines.append(f"• 即時點位：{current_price:,.0f}\n")
    
    trend = advice.get('trend', {})
    lines.append(f"📊 整體趨勢：{trend.get('overall_trend', '未知')}")
    entry = advice.get('entry', {})
    lines.append(f"📌 進場建議：{entry.get('direction', '觀望')}")
    lines.append(f"   理由：{entry.get('reason', '-')}\n")
    
    sl_list = advice.get('stop_loss', [])
    if sl_list:
        lines.append("🛑 建議停損點位 (Stop Loss)：")
        for sl in sl_list:
            lines.append(f"   - [{sl['label']}] {sl['price']:,.0f} (距離 {sl['distance']:,.0f} 點)")
        lines.append("")
        
    tp_list = advice.get('take_profit', [])
    if tp_list:
        lines.append("🎯 建議停利點位 (Take Profit)：")
        for tp in tp_list:
            lines.append(f"   - [{tp['label']}] {tp['price']:,.0f} (距離 {tp['distance']:,.0f} 點)")
        lines.append("")
        
    lines.append("📍 附近 key PRZ 價位 (相同點位已合併去重)：")
    for lvl in nearby_prz.get('above', [])[:3]:
        combos = " | ".join(lvl.get('combo_details', []))
        count = lvl.get('combo_count', 1)
        lines.append(f"   - 上方壓力：{lvl['price']:,.0f} [{count}組組合: {combos}]")
    for lvl in nearby_prz.get('below', [])[:3]:
        combos = " | ".join(lvl.get('combo_details', []))
        count = lvl.get('combo_count', 1)
        lines.append(f"   - 下方支撐：{lvl['price']:,.0f} [{count}組組合: {combos}]")
        
    lines.append("\n系統提示: 本郵件由 C:\\monitor_PRZ 系統自動發送。")
    return "\n".join(lines)


def run_analysis(position=None, send_mail=False):
    print("\n⏳ 正在抓取台指期即時資料...")
    current_price, latest_ts = get_current_price()
    
    if current_price is None:
        print("❌ 無法取得即時價格，請檢查網路連線或 API 狀態。")
        return None
    
    print_header(current_price, latest_ts)
    
    print("\n⏳ 正在抓取多時間框架 K 線資料（日K/15分K/5分K/1分K）...")
    all_data = fetch_all_timeframes()
    
    for tf, df in all_data.items():
        if df.empty:
            print(f"  ⚠️ {TF_NAMES.get(tf, tf)} 資料為空")
        else:
            print(f"  ✅ {TF_NAMES.get(tf, tf)}: {len(df)} 根 K 線")
    
    print("\n⏳ 正在偵測多時間框架 Swing 轉折點...")
    all_swings = get_multi_timeframe_swings(all_data)
    print_swing_section(all_swings, all_data)
    
    print("\n⏳ 正在計算 PRZ 黃金分割位...")
    tf_pairs = build_multi_tf_swing_pairs(all_swings)
    
    if not tf_pairs:
        print("  ❌ 無法找到足夠的 Swing 點來計算 PRZ")
        return None
    
    all_prz = calculate_multi_timeframe_prz(tf_pairs)
    prz_with_resonance = find_resonance_zones(all_prz)
    nearby_prz = print_prz_section(current_price, prz_with_resonance)
    
    print("\n⏳ 正在生成交易建議...")
    trend_swings = build_trend_swings(all_swings)
    trend_info = determine_trend(trend_swings)
    flat_prz = build_flat_prz_for_advisor(prz_with_resonance)
    
    advisor_nearby = {
        'support': [lvl for lvl in flat_prz if lvl['type'] == 'support' and lvl['price'] < current_price],
        'resistance': [lvl for lvl in flat_prz if lvl['type'] == 'resistance' and lvl['price'] > current_price]
    }
    advisor_nearby['support'].sort(key=lambda x: x['price'], reverse=True)
    advisor_nearby['resistance'].sort(key=lambda x: x['price'])
    
    advice = generate_full_advice(
        current_price=current_price,
        nearby_prz=advisor_nearby,
        trend_info=trend_info,
        prz_levels=flat_prz,
        has_position=position
    )
    
    print_trade_advice(advice)
    
    if send_mail:
        print("\n📧 正在寄送分析報告至 Gmail...")
        subject = f"【台指期 PRZ 報告】當前點位 {current_price:,.0f} - {advice['entry'].get('direction', '觀望')}"
        body = build_email_body(current_price, nearby_prz, advice)
        send_email_report(subject, body)
        
    return current_price, advice


def interactive_menu():
    while True:
        print("\n" + "=" * 55)
        print("     🎮 台指期 PRZ 分析互動選單")
        print("=" * 55)
        print("  1. 🔍 全盤趨勢與進場點位分析 (無持倉)")
        print("  2. 🟢 手上有【多單】(計算 3 個停損與 3 個停利)")
        print("  3. 🔴 手上有【空單】(計算 3 個停損與 3 個停利)")
        print("  4. 📧 執行分析並發送 Email 通知報告")
        print("  5. 📖 查看 PRZ 黃金分割理論說明")
        print("  0. 🚪 離開程式")
        print("=" * 55)
        
        choice = input("請選擇操作功能 [0-5]: ").strip()
        
        if choice == '1':
            run_analysis(position=None, send_mail=False)
        elif choice == '2':
            run_analysis(position='long', send_mail=False)
        elif choice == '3':
            run_analysis(position='short', send_mail=False)
        elif choice == '4':
            pos_choice = input("請選擇持倉狀況 (1.無持倉 / 2.多單 / 3.空單): ").strip()
            pos_map = {'1': None, '2': 'long', '3': 'short'}
            pos = pos_map.get(pos_choice, None)
            run_analysis(position=pos, send_mail=True)
        elif choice == '5':
            print_prz_theory()
        elif choice == '0':
            print("\n👋 感謝使用 PRZ 諧波交易分析系統！祝交易順利！")
            break
        else:
            print("⚠️ 無效的選擇，請重新輸入。")


def main():
    parser = argparse.ArgumentParser(description='台指期 PRZ 諧波交易分析系統')
    parser.add_argument('--position', '-p', choices=['long', 'short'],
                        help='目前持倉方向 (long=多單, short=空單)')
    parser.add_argument('--email', '-e', action='store_true',
                        help='發送 Email 通知')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='啟動互動選單模式')
    parser.add_argument('--theory', '-t', action='store_true',
                        help='顯示 PRZ 理論說明')
    args = parser.parse_args()
    
    if args.interactive or (len(sys.argv) == 1 and sys.stdin.isatty()):
        interactive_menu()
    else:
        run_analysis(position=args.position, send_mail=args.email)
        if args.theory:
            print_prz_theory()

if __name__ == '__main__':
    main()
