"""
台指期 PRZ 多模式分析系統 (含雙演算法優點融合模式)
=================================================
當執行本程式時，可選擇：
  1. 【模式 1】Scott Carney 5-Bar Fractal 碎形動態過濾法 (短線敏捷)
  2. 【模式 2】Bryce Gilmore 權威雙箱體模型 (日線鎖定 46,994 上點 / 40,779 下點)
  3. 🔥【模式 3】雙演算法優點融合模式 (日線權威箱體 + 短線 5-Bar 碎形動態過濾 - 兼具宏觀支撐與微觀敏捷)
"""

import sys
import os
import argparse
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')

from data_fetcher import fetch_kline, get_current_price, fetch_all_timeframes
from swing_detector import get_multi_timeframe_swings as get_fractal_swings
from box_swing_detector import get_box_model_swings, explain_box_origin, DAILY_MASTER_HIGH, DAILY_MASTER_LOW
from hybrid_swing_detector import get_hybrid_swings, explain_hybrid_model
from prz_calculator import (
    calculate_multi_timeframe_prz,
    group_prz_levels,
    get_grouped_nearby_prz
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

def print_header(current_price, timestamp, mode_name):
    tz_tw = timezone(timedelta(hours=8))
    now = datetime.now(tz_tw)
    
    print("=" * 65)
    print("       🏛️  台指期 PRZ 諧波交易分析系統  🏛️")
    print(f"       當前選用模式: 【{mode_name}】")
    print("=" * 65)
    print(f"  ⏰ 分析時間: {now.strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)")
    
    if timestamp is not None:
        ts_str = timestamp.strftime('%Y-%m-%d %H:%M:%S') if hasattr(timestamp, 'strftime') else str(timestamp)
        print(f"  📡 資料時間: {ts_str}")
    
    print(f"  📊 台指期即時點位: {current_price:,.0f}")
    print("=" * 65)


def print_swing_section(all_swings, mode):
    print()
    print("━" * 65)
    if mode == 1:
        mode_title = "Scott Carney 5-Bar Fractal 碎形動態過濾"
    elif mode == 2:
        mode_title = "Bryce Gilmore 權威雙箱體模型 (日線 46994/40779)"
    else:
        mode_title = "🔥 雙演算法融合模式 (日線權威箱體 + 短線 5-Bar 碎形)"
        
    print(f"  📐 多時間框架 Swing 轉折點（{mode_title}）")
    print("━" * 65)
    
    for tf in ['D', '15', '5', '1']:
        if tf not in all_swings:
            continue
        
        swings = all_swings[tf]
        highs = swings.get('highs', None)
        lows = swings.get('lows', None)
        
        tf_name = TF_NAMES.get(tf, tf)
        print(f"\n  🔹 {tf_name} 級別:")
        
        if (mode in [2, 3]) and tf == 'D':
            print(f"     📌 權威日線主上點 (Master High): 46,994 (2026-06-03 頂部)")
            print(f"     📌 權威日線主下點 (Master Low):  40,779 (2026-06-08 恐慌箱底)")
            print(f"     📌 中間分界水線 (Waterline)   : 43,886.5")
            print(f"     📌 雙箱體總高度 ΔH           : 6,215 點 (46,994 ~ 40,779)")
            continue
        
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


def print_prz_section(current_price, prz_levels, mode=1):
    nearby = get_grouped_nearby_prz(current_price, prz_levels, n_min=3)
    
    print()
    print("━" * 65)
    mode_str = "僅 5分K & 1分K" if mode == 1 else ("雙箱體大框架 + 短線" if mode == 2 else "🔥 雙模型超級共振 (日線箱體 + 短線 5分/1分 碎形)")
    print(f"  🎯 PRZ 潛在反轉區（{mode_str}）")
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
            
            if mode == 3 and count >= 2:
                res_tag = f"🔥雙模型超級共振 {count}組組合"
            else:
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
            
            if mode == 3 and count >= 2:
                res_tag = f"🔥雙模型超級共振 {count}組組合"
            else:
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
    print("  💡 交易與停損停利建議（結合日線大方向）")
    print("━" * 65)
    
    trend = advice.get('trend', {})
    overall = trend.get('overall_trend', '未知')
    daily_macro = trend.get('daily_macro', '未知')
    
    overall_emoji = {'偏多': '🟢', '偏空': '🔴', '中性': '🟡'}.get(overall, '⚪')
    daily_emoji = {'偏多': '🟢', '偏空': '🔴', '中性': '🟡'}.get(daily_macro, '⚪')
    
    print(f"\n  🏛️ 日線大方向 (Daily Macro Structure): {daily_emoji} {daily_macro}")
    print(f"  🔰 綜合趨勢研判: {overall_emoji} {overall}")
    
    tf_labels = {'daily': '日K線 (大方向)', '15min': '15分K', '5min': '5分K', '1min': '1分K'}
    for tf_key in ['daily', '15min', '5min', '1min']:
        if tf_key in trend:
            emoji = {'偏多': '🟢', '偏空': '🔴', '中性': '🟡'}.get(trend[tf_key], '⚪')
            lbl = tf_labels.get(tf_key, tf_key)
            print(f"     {lbl}: {emoji} {trend[tf_key]}")
            
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
            prz_tag = f" [{tp['prz_name']}]" if sl_list and i < len(sl_list) else ""
            print(f"     {label} [{tp['label']}停利]: {tp['price']:>10,.0f}  "
                  f"(距離當前: {tp['distance']:>6,.0f} 點){prz_tag}")
    else:
        print(f"\n  🎯 停利建議: 無部位或目前建議觀望")


def run_analysis(mode=1, position=None, send_mail=False):
    if mode == 1:
        mode_name = "Scott Carney 5-Bar Fractal 碎形法"
    elif mode == 2:
        mode_name = "Bryce Gilmore 權威雙箱體模型 (日線 46994/40779)"
    else:
        mode_name = "🔥 雙演算法優點融合模式 (日線權威箱體 + 短線 5-Bar 碎形)"
    
    print("\n⏳ 正在抓取台指期即時資料...")
    current_price, latest_ts = get_current_price()
    
    if current_price is None:
        print("❌ 無法取得即時價格，請檢查網路連線或 API 狀態。")
        return None
    
    print_header(current_price, latest_ts, mode_name)
    
    print("\n⏳ 正在抓取多時間框架 K 線資料（日K/15分K/5分K/1分K）...")
    all_data = fetch_all_timeframes()
    
    for tf, df in all_data.items():
        if df.empty:
            print(f"  ⚠️ {TF_NAMES.get(tf, tf)} 資料為空")
        else:
            print(f"  ✅ {TF_NAMES.get(tf, tf)}: {len(df)} 根 K 線")
    
    print(f"\n⏳ 正在使用【{mode_name}】計算多時間框架 Swing 轉折點...")
    if mode == 1:
        all_swings = get_fractal_swings(all_data)
    elif mode == 2:
        all_swings = get_box_model_swings(all_data)
    else:
        all_swings = get_hybrid_swings(all_data)
        
    print_swing_section(all_swings, mode)
    
    print("\n⏳ 正在計算 PRZ 黃金分割位...")
    tf_pairs = build_multi_tf_swing_pairs(all_swings, target_tfs=['5', '1'])
    
    if mode in [2, 3]:
        # 將日線權威雙箱體 (46,994 ~ 40,779) 作為宏觀背景加入 PRZ 共振矩陣
        tf_pairs['日線權威箱體'] = (DAILY_MASTER_HIGH, DAILY_MASTER_LOW)
        
    all_prz = calculate_multi_timeframe_prz(tf_pairs)
    grouped_prz = group_prz_levels(all_prz, tolerance_points=3.0)
    nearby_prz = print_prz_section(current_price, grouped_prz, mode=mode)
    
    print("\n⏳ 正在生成交易與停損停利建議...")
    trend_swings = build_trend_swings(all_swings)
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
        has_position=position
    )
    
    print_trade_advice(advice)
    return current_price, advice


def main():
    parser = argparse.ArgumentParser(description='台指期 PRZ 多模式分析系統 (含融合演算法)')
    parser.add_argument('--mode', '-m', type=int, choices=[1, 2, 3],
                        help='選擇轉折點計算模式 (1=5-Bar Fractal碎形法, 2=雙箱體模型, 3=雙演算法優點融合模式)')
    parser.add_argument('--position', '-p', choices=['long', 'short'],
                        help='目前持倉方向 (long=多單, short=空單)')
    parser.add_argument('--explain', '-e', action='store_true',
                        help='解釋轉折點演算法由來與融合模式原理')
    args = parser.parse_args()
    
    if args.explain:
        print(explain_box_origin())
        print(explain_hybrid_model())
        return
        
    mode = args.mode
    if mode is None:
        print("\n" + "=" * 65)
        print("  🤔 請選擇 PRZ 轉折點計算模式 (Swing Pivot Model):")
        print("=" * 65)
        print("  1. 經典 Scott Carney 5-Bar Fractal 碎形過濾模式")
        print("     (動態搜尋多時間框架左右各 2 根包夾之短線 Swing Pivot)")
        print()
        print("  2. 權威 Bryce Gilmore 雙箱體結構模型模式")
        print("     (日線固定錨定主上點 46,994 / 主下點 40,779，中間水線 43,886.5)")
        print()
        print("  3. 🔥 【雙演算法優點融合模式】 (推薦！巨觀日線箱體 + 微觀 5分/1分 碎形)")
        print("     (日線鎖定 46,994/40,779 宏觀防線 + 盤中動態搜尋，觸發超級共振！)")
        print()
        print("  4. 📖 閱讀兩大演算法由來與融合模式理論解析")
        print("=" * 65)
        
        user_input = input("請輸入選擇 [1/2/3/4] (預設為 3 融合模式): ").strip()
        if user_input == '1':
            mode = 1
        elif user_input == '2':
            mode = 2
        elif user_input == '4':
            print(explain_box_origin())
            print(explain_hybrid_model())
            return
        else:
            mode = 3
            
    pos = args.position
    if pos is None:
        print("\n" + "-" * 50)
        print("  請選擇當前持倉狀態:")
        print("  1. ⚪ 目前空手 (無部位，尋求進場建議)")
        print("  2. 🟢 手上有【多單】(計算專屬 3 個停損與 3 個停利)")
        print("  3. 🔴 手上有【空單】(計算專屬 3 個停損與 3 個停利)")
        print("-" * 50)
        pos_input = input("請輸入選擇 [1/2/3] (預設為 1): ").strip()
        if pos_input == '2':
            pos = 'long'
        elif pos_input == '3':
            pos = 'short'
        else:
            pos = None
            
    run_analysis(mode=mode, position=pos, send_mail=False)

if __name__ == '__main__':
    main()
