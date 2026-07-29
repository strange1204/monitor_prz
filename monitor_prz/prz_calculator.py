import sys
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple

sys.stdout.reconfigure(encoding='utf-8')

FIB_RATIOS = {
    'retracement': [
        (0.236, '淺層回撤 (Φ⁻³)'),
        (0.382, '標準回撤 (Φ⁻²)'),
        (0.500, '中心回撤'),
        (0.618, '深度回撤 (Φ⁻¹)'),
        (0.786, '加特利回撤 (√0.618)'),
        (0.886, '蝙蝠極限位 (√0.786)'),
    ],
    'extension': [
        (1.130, '陷阱區 (⁴√1.618) 假突破/假跌破'),
        (1.272, '蝴蝶延伸 (√1.618)'),
        (1.618, '螃蟹延伸 (Φ)'),
    ]
}

def calculate_prz_levels(swing_high: float, swing_low: float, source: str = "default") -> List[Dict[str, Any]]:
    """
    計算 PRZ (潛在反轉區) 水位。
    """
    delta_h = swing_high - swing_low
    levels = []
    
    for ratio, name in FIB_RATIOS['retracement']:
        # 向下回撤 (尋找支撐)
        support_price = swing_high - delta_h * ratio
        levels.append({
            'price': support_price,
            'ratio': ratio,
            'name': name,
            'direction': 'support',
            'source': source
        })
        
        # 向上反彈 (尋找壓力)
        resistance_price = swing_low + delta_h * ratio
        levels.append({
            'price': resistance_price,
            'ratio': ratio,
            'name': name,
            'direction': 'resistance',
            'source': source
        })
        
    for ratio, name in FIB_RATIOS['extension']:
        # 向上延伸
        ext_up = swing_high + delta_h * (ratio - 1)
        levels.append({
            'price': ext_up,
            'ratio': ratio,
            'name': name,
            'direction': 'extension_up',
            'source': source
        })
        
        # 向下延伸
        ext_down = swing_low - delta_h * (ratio - 1)
        levels.append({
            'price': ext_down,
            'ratio': ratio,
            'name': name,
            'direction': 'extension_down',
            'source': source
        })
        
    return levels

def calculate_multi_timeframe_prz(multi_tf_swings: Dict[str, Tuple[float, float]]) -> List[Dict[str, Any]]:
    """
    計算多時間級別的 PRZ 水位。
    """
    all_levels = []
    for tf, (high, low) in multi_tf_swings.items():
        levels = calculate_prz_levels(high, low, source=tf)
        all_levels.extend(levels)
        
    all_levels.sort(key=lambda x: x['price'])
    return all_levels

def group_prz_levels(prz_levels: List[Dict[str, Any]], tolerance_points: float = 3.0) -> List[Dict[str, Any]]:
    """
    將相同或極相近的 PRZ 價位進行分組整合（相同點位合併為一筆）。
    統計包含幾個組合以及具體有哪些組合（時間框架 + 比率 + 比例名稱）。
    """
    if not prz_levels:
        return []
        
    sorted_levels = sorted(prz_levels, key=lambda x: x['price'])
    grouped = []
    current_group = []
    
    for lvl in sorted_levels:
        if not current_group:
            current_group.append(lvl)
        else:
            base_price = current_group[0]['price']
            if abs(lvl['price'] - base_price) <= tolerance_points:
                current_group.append(lvl)
            else:
                grouped.append(current_group)
                current_group = [lvl]
    if current_group:
        grouped.append(current_group)
        
    result_levels = []
    for grp in grouped:
        avg_price = sum(item['price'] for item in grp) / len(grp)
        rounded_price = round(avg_price)
        
        combo_details = []
        seen_combos = set()
        sources = set()
        
        for item in grp:
            if 'combo_details' in item and item['combo_details']:
                for c in item['combo_details']:
                    if c not in seen_combos:
                        seen_combos.add(c)
                        combo_details.append(c)
                for s in item.get('sources', []):
                    sources.add(s)
            else:
                src = item.get('source', '')
                sources.add(src)
                ratio = item.get('ratio', 0)
                name = item.get('name', '')
                combo_str = f"{src} {ratio:.3f} {name}"
                if combo_str not in seen_combos:
                    seen_combos.add(combo_str)
                    combo_details.append(combo_str)
                
        is_res = (len(grp) >= 2) or (len(sources) >= 2)
        direction = grp[0].get('direction', 'support')
        
        result_levels.append({
            'price': rounded_price,
            'float_price': avg_price,
            'combo_count': len(grp),
            'combo_details': combo_details,
            'sources': list(sources),
            'is_resonance': is_res,
            'direction': direction,
            'raw_items': grp
        })
        
    return result_levels

def get_grouped_nearby_prz(current_price: float, prz_levels: List[Dict[str, Any]], n_min: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """
    找出距離當前價格最近的 PRZ 水位（合併相同點位）。
    確保上方壓力與下方支撐各輸出「至少 n_min 個 (預設3個)」獨立點位。
    """
    grouped = group_prz_levels(prz_levels, tolerance_points=3.0)
    
    above = [g for g in grouped if g['price'] >= current_price]
    below = [g for g in grouped if g['price'] < current_price]
    
    above_sorted = sorted(above, key=lambda x: x['price'])
    below_sorted = sorted(below, key=lambda x: x['price'], reverse=True)
    
    num_above = max(n_min, min(6, len(above_sorted)))
    num_below = max(n_min, min(6, len(below_sorted)))
    
    return {
        'above': above_sorted[:num_above],
        'below': below_sorted[:num_below]
    }

def find_resonance_zones(all_prz_levels: List[Dict[str, Any]], tolerance_pct: float = 0.003) -> List[Dict[str, Any]]:
    """
    保留原有介面相容性
    """
    if not all_prz_levels:
        return []
    return group_prz_levels(all_prz_levels, tolerance_points=3.0)

def get_nearby_prz(current_price: float, prz_levels: List[Dict[str, Any]], n: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """
    保留原有介面相容性，調用分組近端點位
    """
    return get_grouped_nearby_prz(current_price, prz_levels, n_min=n)

def format_prz_report(current_price: float, nearby_prz: Dict[str, List[Dict[str, Any]]]) -> str:
    """
    格式化 PRZ 報告。
    """
    lines = [f"當前價格: {current_price:.2f}"]
    lines.append("=" * 40)
    
    lines.append("上方阻力 (Above PRZ):")
    for lvl in reversed(nearby_prz.get('above', [])):
        dist = lvl['price'] - current_price
        dist_pct = (dist / current_price) * 100
        icon = "⭐" if lvl.get('is_resonance') else "📍"
        combos = " / ".join(lvl.get('combo_details', []))
        line = (f"{icon} 價格: {lvl['price']} | 距離: +{dist:.0f} (+{dist_pct:.2f}%) | "
                f"[{lvl['combo_count']}組組合: {combos}]")
        lines.append(line)
        
    lines.append("-" * 40)
    lines.append("下方支撐 (Below PRZ):")
    for lvl in nearby_prz.get('below', []):
        dist = current_price - lvl['price']
        dist_pct = (dist / current_price) * 100
        icon = "⭐" if lvl.get('is_resonance') else "📍"
        combos = " / ".join(lvl.get('combo_details', []))
        line = (f"{icon} 價格: {lvl['price']} | 距離: -{dist:.0f} (-{dist_pct:.2f}%) | "
                f"[{lvl['combo_count']}組組合: {combos}]")
        lines.append(line)
        
    lines.append("=" * 40)
    return "\n".join(lines)
