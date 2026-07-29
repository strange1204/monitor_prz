import sys
import pandas as pd
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

def determine_trend(multi_tf_swings):
    """
    根據多時間週期的波段高低點判斷整體趨勢（包含日線大方向）。
    """
    trends = {}
    bull_count = 0
    bear_count = 0
    
    for tf, swings in multi_tf_swings.items():
        if len(swings) < 4:
            trends[tf] = '中性'
            continue
            
        highs = [s['price'] for s in swings if s['type'] == 'high']
        lows = [s['price'] for s in swings if s['type'] == 'low']
        
        if len(highs) >= 2 and len(lows) >= 2:
            if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
                trends[tf] = '偏多'
                if tf == 'daily':
                    bull_count += 2  # 日線大方向加重權重
                else:
                    bull_count += 1
            elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
                trends[tf] = '偏空'
                if tf == 'daily':
                    bear_count += 2  # 日線大方向加重權重
                else:
                    bear_count += 1
            else:
                trends[tf] = '中性'
        else:
            trends[tf] = '中性'
            
    if bull_count > bear_count:
        overall_trend = '偏多'
    elif bear_count > bull_count:
        overall_trend = '偏空'
    else:
        overall_trend = '中性'
        
    trends['overall_trend'] = overall_trend
    trends['daily_macro'] = trends.get('daily', '中性')
    return trends


def generate_entry_advice(current_price, nearby_prz, trend_info):
    """
    根據目前價格與近期 PRZ 的相對位置以及趨勢（含日線大方向），產生進場建議。
    """
    overall_trend = trend_info.get('overall_trend', '中性')
    daily_macro = trend_info.get('daily_macro', '中性')
    
    direction = '觀望'
    entry_zone = None
    confidence = '低'
    reason = '無明顯進場訊號'
    
    support = nearby_prz.get('support', [])
    resistance = nearby_prz.get('resistance', [])
    
    nearest_support = support[0] if support else None
    nearest_resistance = resistance[0] if resistance else None
    
    dist_to_support = (current_price - nearest_support['price']) if nearest_support else float('inf')
    dist_to_resistance = (nearest_resistance['price'] - current_price) if nearest_resistance else float('inf')
    
    NEAR_THRESHOLD = 150
    
    macro_prefix = f"【日線大方向: {daily_macro}】"
    
    if overall_trend == '偏多':
        if nearest_support and dist_to_support <= NEAR_THRESHOLD and dist_to_support >= 0:
            direction = '做多'
            entry_zone = (nearest_support['price'], nearest_support['price'] + 50)
            confidence = '高' if nearest_support.get('is_resonance', False) else '中'
            reason = f"{macro_prefix} 短線多頭排列，價格接近近端支撐位 {nearest_support['price']:,.0f}（距離 {dist_to_support:,.0f} 點），建議逢低做多。"
        elif nearest_support and dist_to_support > NEAR_THRESHOLD:
            direction = '做多'
            entry_zone = (nearest_support['price'], nearest_support['price'] + 50)
            confidence = '低'
            reason = f"{macro_prefix} 短線偏多，但距最近支撐 {nearest_support['price']:,.0f} 尚有 {dist_to_support:,.0f} 點，建議等待拉回再進場。"
        else:
            reason = f"{macro_prefix} 趨勢偏多，但無明確近端支撐位可參考。"
    elif overall_trend == '偏空':
        if nearest_resistance and dist_to_resistance <= NEAR_THRESHOLD and dist_to_resistance >= 0:
            direction = '做空'
            entry_zone = (nearest_resistance['price'] - 50, nearest_resistance['price'])
            confidence = '高' if nearest_resistance.get('is_resonance', False) else '中'
            reason = f"{macro_prefix} 短線空頭排列，價格接近近端壓力位 {nearest_resistance['price']:,.0f}（距離 {dist_to_resistance:,.0f} 點），建議逢高做空。"
        elif nearest_resistance and dist_to_resistance > NEAR_THRESHOLD:
            direction = '做空'
            entry_zone = (nearest_resistance['price'] - 50, nearest_resistance['price'])
            confidence = '低'
            reason = f"{macro_prefix} 短線偏空，但距最近壓力 {nearest_resistance['price']:,.0f} 尚有 {dist_to_resistance:,.0f} 點，建議等待反彈再進場。"
        else:
            reason = f"{macro_prefix} 趨勢偏空，但無明確近端壓力位可參考。"
    else:  # 中性
        if nearest_support and dist_to_support <= NEAR_THRESHOLD:
            direction = '做多'
            entry_zone = (nearest_support['price'], nearest_support['price'] + 50)
            confidence = '低'
            reason = f"{macro_prefix} 趨勢中性震盪，價格接近支撐位 {nearest_support['price']:,.0f}（距離 {dist_to_support:,.0f} 點），可嘗試輕倉做多。"
        elif nearest_resistance and dist_to_resistance <= NEAR_THRESHOLD:
            direction = '做空'
            entry_zone = (nearest_resistance['price'] - 50, nearest_resistance['price'])
            confidence = '低'
            reason = f"{macro_prefix} 趨勢中性震盪，價格接近壓力位 {nearest_resistance['price']:,.0f}（距離 {dist_to_resistance:,.0f} 點），可嘗試輕倉做空。"
        else:
            reason = f"{macro_prefix} 盤態中性，距最近支撐 {dist_to_support:,.0f} 點 / 距最近壓力 {dist_to_resistance:,.0f} 點，建議觀望。"
                
    return {
        'direction': direction,
        'entry_zone': entry_zone,
        'confidence': confidence,
        'reason': reason
    }


def generate_stop_loss(current_price, nearby_prz, direction, prz_levels):
    """
    產生停損建議（至少 3 個獨立位階）。
    """
    stop_losses = []
    SL_OFFSET = 20
    
    if direction in ['做多', 'long']:
        supports = [p for p in prz_levels if p['type'] == 'support' and p['price'] < current_price]
        supports.sort(key=lambda x: x['price'], reverse=True)
        
        seen_prices = set()
        unique_supports = []
        for s in supports:
            rounded = round(s['price'])
            if rounded not in seen_prices:
                seen_prices.add(rounded)
                unique_supports.append(s)
        
        labels = [('保守', '最近支撐下方'), ('標準', '第二支撐下方'), ('積極', '第三支撐下方')]
        for i, (label, desc) in enumerate(labels):
            if i < len(unique_supports):
                sl = unique_supports[i]['price'] - SL_OFFSET
                stop_losses.append({
                    'price': sl, 
                    'label': label, 
                    'distance': current_price - sl,
                    'prz_name': unique_supports[i].get('name', '')
                })
            
    elif direction in ['做空', 'short']:
        resistances = [p for p in prz_levels if p['type'] == 'resistance' and p['price'] > current_price]
        resistances.sort(key=lambda x: x['price'])
        
        seen_prices = set()
        unique_resistances = []
        for r in resistances:
            rounded = round(r['price'])
            if rounded not in seen_prices:
                seen_prices.add(rounded)
                unique_resistances.append(r)
        
        labels = [('保守', '最近壓力上方'), ('標準', '第二壓力上方'), ('積極', '第三壓力上方')]
        for i, (label, desc) in enumerate(labels):
            if i < len(unique_resistances):
                sl = unique_resistances[i]['price'] + SL_OFFSET
                stop_losses.append({
                    'price': sl, 
                    'label': label, 
                    'distance': sl - current_price,
                    'prz_name': unique_resistances[i].get('name', '')
                })
            
    return stop_losses


def generate_take_profit(current_price, nearby_prz, direction, prz_levels):
    """
    產生停利建議（至少 3 個獨立位階）。
    """
    take_profits = []
    
    def _dedupe(levels):
        seen = set()
        unique = []
        for lvl in levels:
            rounded = round(lvl['price'])
            if rounded not in seen:
                seen.add(rounded)
                unique.append(lvl)
        return unique
    
    if direction in ['做多', 'long']:
        resistances = [p for p in prz_levels if p['type'] == 'resistance' and p['price'] > current_price]
        resistances.sort(key=lambda x: x['price'])
        resistances = _dedupe(resistances)
        
        labels = ['保守', '標準', '積極']
        for i, label in enumerate(labels):
            if i < len(resistances):
                tp = resistances[i]['price']
                take_profits.append({
                    'price': tp, 
                    'label': label, 
                    'distance': tp - current_price,
                    'prz_name': resistances[i].get('name', '')
                })
            
    elif direction in ['做空', 'short']:
        supports = [p for p in prz_levels if p['type'] == 'support' and p['price'] < current_price]
        supports.sort(key=lambda x: x['price'], reverse=True)
        supports = _dedupe(supports)
        
        labels = ['保守', '標準', '積極']
        for i, label in enumerate(labels):
            if i < len(supports):
                tp = supports[i]['price']
                take_profits.append({
                    'price': tp, 
                    'label': label, 
                    'distance': current_price - tp,
                    'prz_name': supports[i].get('name', '')
                })
            
    return take_profits


def generate_full_advice(current_price, nearby_prz, trend_info, prz_levels, has_position=None):
    """
    統整產生完整的交易建議。
    """
    daily_macro = trend_info.get('daily_macro', '中性')
    
    if has_position == 'long':
        direction = '做多'
        entry_advice = {'direction': '做多 (持倉中)', 'entry_zone': None, 'confidence': '-', 'reason': f'【日線大方向: {daily_macro}】手上已有多單，以下提供專屬停損與停利建議。'}
    elif has_position == 'short':
        direction = '做空'
        entry_advice = {'direction': '做空 (持倉中)', 'entry_zone': None, 'confidence': '-', 'reason': f'【日線大方向: {daily_macro}】手上已有空單，以下提供專屬停損與停利建議。'}
    else:
        entry_advice = generate_entry_advice(current_price, nearby_prz, trend_info)
        direction = entry_advice['direction']
        
    advice = {
        'current_price': current_price,
        'trend': trend_info,
        'entry': entry_advice,
        'stop_loss': generate_stop_loss(current_price, nearby_prz, direction, prz_levels) if direction in ['做多', '做空', 'long', 'short'] else [],
        'take_profit': generate_take_profit(current_price, nearby_prz, direction, prz_levels) if direction in ['做多', '做空', 'long', 'short'] else []
    }
    return advice


def format_advice_report(advice):
    """
    將交易建議格式化為文字報告。
    """
    report = []
    report.append("="*40)
    report.append("📊 PRZ 交易建議報告")
    report.append(f"💰 目前價格: {advice.get('current_price', 0):.2f}")
    report.append("="*40)
    
    trend_info = advice.get('trend', {})
    overall = trend_info.get('overall_trend', '未知')
    daily_macro = trend_info.get('daily_macro', '未知')
    
    report.append(f"\n🏛️ 日線大方向: {daily_macro}")
    report.append(f"🔰 整體綜合趨勢: {overall}")
    
    tf_map_name = {'daily': '日K線 (大方向)', '15min': '15分K', '5min': '5分K', '1min': '1分K'}
    for tf, tr in trend_info.items():
        if tf not in ['overall_trend', 'daily_macro']:
            name = tf_map_name.get(tf, tf)
            report.append(f"   - {name}: {tr}")
            
    entry = advice.get('entry', {})
    report.append(f"\n📌 進場建議: {entry.get('direction', '觀望')}")
    if entry.get('entry_zone'):
        report.append(f"   - 建議區間: {entry['entry_zone'][0]:.2f} - {entry['entry_zone'][1]:.2f}")
    report.append(f"   - 信心水準: {entry.get('confidence', '-')}")
    report.append(f"   - 判斷理由: {entry.get('reason', '-')}")
    
    sl_list = advice.get('stop_loss', [])
    if sl_list:
        report.append("\n🛑 停損設定 (Stop Loss):")
        for sl in sl_list:
            report.append(f"   - [{sl['label']}] 點位: {sl['price']:.2f} (距離: {sl['distance']:.2f} 點)")
            
    tp_list = advice.get('take_profit', [])
    if tp_list:
        report.append("\n🎯 停利設定 (Take Profit):")
        for tp in tp_list:
            report.append(f"   - [{tp['label']}] 點位: {tp['price']:.2f} (距離: {tp['distance']:.2f} 點)")
            
    report.append("\n" + "="*40)
    return "\n".join(report)
