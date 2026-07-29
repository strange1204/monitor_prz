"""
10年期 PRZ 諧波交易策略遞迴歷史回測與驗證系統 (Backtesting Engine v3.0)
=============================================================
1. 抓取近 10 年 (2016 - 2026) 台指期 / 加權日 K 線數據 (2,428 筆交易日)
2. 逐年 (Yearly) 滾動式計算，每當完成一個年份時，自動發送 Email 通報
3. 統計【逐年勝率】與【累計勝率】，並輸出結果至 GitHub 暫存 (Artifact)
4. 內建 3 次失敗保護機制 (3-Strike Rule Safety Guard)
"""

import sys
import os
import time
import json
import urllib.request
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')

# 匯入 PRZ 分析與 Email 模組
from hybrid_swing_detector import get_hybrid_swings
from box_swing_detector import get_box_model_swings, DAILY_MASTER_HIGH, DAILY_MASTER_LOW
from swing_detector import get_multi_timeframe_swings as get_fractal_swings
from prz_calculator import calculate_multi_timeframe_prz, group_prz_levels, get_grouped_nearby_prz
from trade_advisor import determine_trend, generate_full_advice
from notifier import send_email_report

class StepBottleneckException(Exception):
    """當單一步驟累積失敗達 3 次時拋出的中斷異常"""
    pass

class StepErrorTracker:
    """步驟異常與瓶頸追蹤器 (3-Strike Rule Guard)"""
    def __init__(self, max_allowed_errors=3):
        self.error_counts = {}
        self.error_logs = {}
        self.max_allowed = max_allowed_errors
        
    def record_error(self, step_name, error_msg):
        count = self.error_counts.get(step_name, 0) + 1
        self.error_counts[step_name] = count
        if step_name not in self.error_logs:
            self.error_logs[step_name] = []
        self.error_logs[step_name].append(error_msg)
        
        print(f"⚠️ [步驟異常警告] {step_name} 發生第 {count}/{self.max_allowed} 次錯誤: {error_msg}")
        
        if count >= self.max_allowed:
            msg = (
                f"\n" + "=" * 65 + "\n"
                f"🚨 【步驟瓶頸中斷討論提示】\n"
                f"步驟 [{step_name}] 已累積失敗 {count} 次，達到安全邊界門檻！\n"
                f"最近三次錯誤記錄：\n" +
                "\n".join([f"  - {err}" for err in self.error_logs[step_name][-3:]]) +
                f"\n程式已安全暫停中斷。請與使用者討論此瓶頸問題後再繼續。\n" +
                "=" * 65 + "\n"
            )
            print(msg)
            raise StepBottleneckException(msg)

def fetch_10y_historical_data(tracker):
    """
    抓取過去 10 年 (2016-2026) 的日 K 線數據
    """
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?range=10y&interval=1d'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    attempts = 0
    while attempts < 3:
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                
            chart_res = data.get('chart', {}).get('result', [])
            if not chart_res:
                tracker.record_error("data_fetching", "API 回應中無有效 chart result")
                attempts += 1
                continue
                
            result = chart_res[0]
            timestamps = result.get('timestamp', [])
            quote = result.get('indicators', {}).get('quote', [{}])[0]
            
            opens = quote.get('open', [])
            highs = quote.get('high', [])
            lows = quote.get('low', [])
            closes = quote.get('close', [])
            volumes = quote.get('volume', [])
            
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(timestamps, unit='s', utc=True).tz_convert('Asia/Taipei'),
                'open': opens,
                'high': highs,
                'low': lows,
                'close': closes,
                'volume': volumes
            }).dropna().reset_index(drop=True)
            
            if len(df) < 500:
                tracker.record_error("data_fetching", f"歷史資料筆數不足 10 年標準 (僅 {len(df)} 筆)")
                attempts += 1
                continue
                
            print(f"✅ 成功獲取 10 年歷史日 K 線數據，共 {len(df)} 筆交易日資料 ({df['timestamp'].iloc[0].strftime('%Y-%m-%d')} ~ {df['timestamp'].iloc[-1].strftime('%Y-%m-%d')})")
            return df
            
        except Exception as e:
            tracker.record_error("data_fetching", f"網路連線或解析失敗: {e}")
            attempts += 1
            time.sleep(1)
            
    return None

def send_yearly_progress_email(year, yearly_stats, cum_stats):
    """
    當完成某年份的回測時，發送 Email 通報逐年與累計勝率
    """
    tz_tw = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_tw).strftime('%Y-%m-%d %H:%M:%S')
    
    subject = f"【PRZ 10年回測進度】{year} 年度已完成 - 逐年勝率: {yearly_stats['win_rate']:.1f}% | 累計勝率: {cum_stats['win_rate']:.1f}%"
    
    body = f"""親愛的 Brian 您好：

台指期 PRZ 諧波交易策略【10年期歷史遞迴回測】進度更新通知！

📅 已完成年份：{year} 年
⏰ 處理時間：{now_str} (台灣時間)

==================================================
📊 【{year} 單一年度績效統計】
  • 逐年交易次數：{yearly_stats['total_trades']} 次
  • 逐年勝場/敗場：{yearly_stats['win_count']} 勝 / {yearly_stats['loss_count']} 敗
  • ⭐ 逐年勝率：{yearly_stats['win_rate']:.2f} %
  • 💰 逐年淨損益：{yearly_stats['pnl']:+,.0f} 點
  • ⚖️ 逐年獲利因子(PF)：{yearly_stats['profit_factor']:.2f}

📈 【自 2016 至 {year} 年 累計績效統計】
  • 累計總交易次數：{cum_stats['total_trades']} 次
  • 累計勝場/敗場：{cum_stats['win_count']} 勝 / {cum_stats['loss_count']} 敗
  • 🏆 累計勝率：{cum_stats['win_rate']:.2f} %
  • 💰 累計總淨損益：{cum_stats['pnl']:+,.0f} 點
  • ⚖️ 累計獲利因子(PF)：{cum_stats['profit_factor']:.2f}
==================================================

詳細資料與 CSV 交易明細已同步儲存於 GitHub Artifact 暫存區。

系統提示: 本郵件由 backtest_prz_strategy.py 自動執行發送。
"""
    print(f"\n📧 正在發送【{year} 年進度通知】至 Email...")
    send_email_report(subject, body)

def run_backtest(df, tracker, mode=3, high_confidence_only=True, max_holding_days=10):
    """
    執行 10 年期滾動式遞迴回測，並於每年處理完畢時觸發 Email 通知與暫存
    """
    trades = []
    total_bars = len(df)
    START_INDEX = 60
    
    filter_label = "高信心水準超級共振濾網" if high_confidence_only else "全訊號基線"
    print(f"\n⏳ 開始執行滾動式遞迴回測 ({filter_label}, 2016-2026)...")
    
    current_processing_year = None
    yearly_report_data = []
    
    i = START_INDEX
    while i < total_bars - max_holding_days:
        try:
            current_bar = df.iloc[i]
            history_slice = df.iloc[max(0, i-180):i+1].copy()
            current_price = current_bar['close']
            bar_year = current_bar['timestamp'].year
            
            # 當跨越到新年份時，結算並發送上一年度的 Email 通知
            if current_processing_year is not None and bar_year != current_processing_year:
                df_all_trades = pd.DataFrame(trades) if trades else pd.DataFrame()
                if not df_all_trades.empty:
                    df_all_trades['year'] = pd.to_datetime(df_all_trades['entry_time']).dt.year
                    
                    # 逐年資料
                    df_year = df_all_trades[df_all_trades['year'] == current_processing_year]
                    if not df_year.empty:
                        y_total = len(df_year)
                        y_wins = len(df_year[df_year['pnl_points'] > 0])
                        y_losses = len(df_year[df_year['pnl_points'] < 0])
                        y_win_rate = (y_wins / y_total) * 100
                        y_pnl = df_year['pnl_points'].sum()
                        g_prof = df_year[df_year['pnl_points'] > 0]['pnl_points'].sum()
                        g_loss = abs(df_year[df_year['pnl_points'] < 0]['pnl_points'].sum())
                        y_pf = (g_prof / g_loss) if g_loss > 0 else float('inf')
                        
                        y_stats = {
                            'year': current_processing_year,
                            'total_trades': y_total,
                            'win_count': y_wins,
                            'loss_count': y_losses,
                            'win_rate': y_win_rate,
                            'pnl': y_pnl,
                            'profit_factor': y_pf
                        }
                        
                        # 累計資料 (從頭至該年份)
                        df_cum = df_all_trades[df_all_trades['year'] <= current_processing_year]
                        c_total = len(df_cum)
                        c_wins = len(df_cum[df_cum['pnl_points'] > 0])
                        c_losses = len(df_cum[df_cum['pnl_points'] < 0])
                        c_win_rate = (c_wins / c_total) * 100
                        c_pnl = df_cum['pnl_points'].sum()
                        cg_prof = df_cum[df_cum['pnl_points'] > 0]['pnl_points'].sum()
                        cg_loss = abs(df_cum[df_cum['pnl_points'] < 0]['pnl_points'].sum())
                        c_pf = (cg_prof / cg_loss) if cg_loss > 0 else float('inf')
                        
                        c_stats = {
                            'total_trades': c_total,
                            'win_count': c_wins,
                            'loss_count': c_losses,
                            'win_rate': c_win_rate,
                            'pnl': c_pnl,
                            'profit_factor': c_pf
                        }
                        
                        yearly_report_data.append({'yearly': y_stats, 'cumulative': c_stats})
                        send_yearly_progress_email(current_processing_year, y_stats, c_stats)
                        
            current_processing_year = bar_year
            
            all_data = {'D': history_slice, '15': pd.DataFrame(), '5': pd.DataFrame(), '1': pd.DataFrame()}
            
            if mode == 1:
                all_swings = get_fractal_swings(all_data)
            elif mode == 2:
                all_swings = get_box_model_swings(all_data)
            else:
                all_swings = get_hybrid_swings(all_data)
                
            tf_pairs = {}
            if 'D' in all_swings and not all_swings['D']['highs'].empty and not all_swings['D']['lows'].empty:
                tf_pairs['日K'] = (history_slice['high'].max(), history_slice['low'].min())
            tf_pairs['日線權威箱體'] = (DAILY_MASTER_HIGH, DAILY_MASTER_LOW)
            
            all_prz = calculate_multi_timeframe_prz(tf_pairs)
            grouped_prz = group_prz_levels(all_prz, tolerance_points=5.0)
            
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
            
            trend_swings = {'daily': [{'type': 'high', 'price': row['price'], 'bar_index': row['bar_index']} for _, row in all_swings['D']['highs'].iterrows()] +
                                     [{'type': 'low', 'price': row['price'], 'bar_index': row['bar_index']} for _, row in all_swings['D']['lows'].iterrows()]}
            trend_info = determine_trend(trend_swings)
            
            advice = generate_full_advice(
                current_price=current_price,
                nearby_prz=advisor_nearby,
                trend_info=trend_info,
                prz_levels=flat_prz,
                has_position=None
            )
            
            entry_info = advice.get('entry', {})
            entry_dir = entry_info.get('direction')
            confidence = entry_info.get('confidence', '低')
            
            if high_confidence_only and confidence != '高':
                i += 1
                continue
                
            if entry_dir in ['做多', '做空']:
                entry_price = df.iloc[i+1]['open']
                entry_time = df.iloc[i+1]['timestamp']
                
                stop_losses = advice.get('stop_loss', [])
                take_profits = advice.get('take_profit', [])
                
                if not stop_losses or not take_profits:
                    i += 1
                    continue
                    
                sl_price = stop_losses[1]['price'] if len(stop_losses) >= 2 else stop_losses[0]['price']
                tp_price = take_profits[0]['price']
                
                trade_result = 'EXPIRE'
                exit_price = current_price
                exit_time = entry_time
                pnl_points = 0
                
                for h in range(1, max_holding_days + 1):
                    if i + 1 + h >= total_bars:
                        break
                    future_bar = df.iloc[i + 1 + h]
                    f_high = future_bar['high']
                    f_low = future_bar['low']
                    
                    if entry_dir == '做多':
                        if f_low <= sl_price:
                            trade_result = 'SL'
                            exit_price = sl_price
                            exit_time = future_bar['timestamp']
                            pnl_points = exit_price - entry_price
                            break
                        elif f_high >= tp_price:
                            trade_result = 'TP1'
                            exit_price = tp_price
                            exit_time = future_bar['timestamp']
                            pnl_points = exit_price - entry_price
                            break
                    elif entry_dir == '做空':
                        if f_high >= sl_price:
                            trade_result = 'SL'
                            exit_price = sl_price
                            exit_time = future_bar['timestamp']
                            pnl_points = entry_price - exit_price
                            break
                        elif f_low <= tp_price:
                            trade_result = 'TP1'
                            exit_price = tp_price
                            exit_time = future_bar['timestamp']
                            pnl_points = entry_price - exit_price
                            break
                            
                if trade_result == 'EXPIRE':
                    expire_bar = df.iloc[min(i + 1 + max_holding_days, total_bars - 1)]
                    exit_price = expire_bar['close']
                    exit_time = expire_bar['timestamp']
                    pnl_points = (exit_price - entry_price) if entry_dir == '做多' else (entry_price - exit_price)
                    
                trades.append({
                    'entry_time': str(entry_time),
                    'exit_time': str(exit_time),
                    'direction': entry_dir,
                    'confidence': confidence,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'result': trade_result,
                    'pnl_points': pnl_points
                })
                
                i += max_holding_days
            else:
                i += 1
                
        except StepBottleneckException:
            raise
        except Exception as e:
            tracker.record_error("trade_simulation", f"第 {i} 日回測計算異常: {e}")
            i += 1
            
    # 最後一年發送通報
    if current_processing_year is not None and trades:
        df_all_trades = pd.DataFrame(trades)
        df_all_trades['year'] = pd.to_datetime(df_all_trades['entry_time']).dt.year
        df_year = df_all_trades[df_all_trades['year'] == current_processing_year]
        if not df_year.empty:
            y_total = len(df_year)
            y_wins = len(df_year[df_year['pnl_points'] > 0])
            y_losses = len(df_year[df_year['pnl_points'] < 0])
            y_win_rate = (y_wins / y_total) * 100
            y_pnl = df_year['pnl_points'].sum()
            g_prof = df_year[df_year['pnl_points'] > 0]['pnl_points'].sum()
            g_loss = abs(df_year[df_year['pnl_points'] < 0]['pnl_points'].sum())
            y_pf = (g_prof / g_loss) if g_loss > 0 else float('inf')
            
            y_stats = {'year': current_processing_year, 'total_trades': y_total, 'win_count': y_wins, 'loss_count': y_losses, 'win_rate': y_win_rate, 'pnl': y_pnl, 'profit_factor': y_pf}
            
            c_total = len(df_all_trades)
            c_wins = len(df_all_trades[df_all_trades['pnl_points'] > 0])
            c_losses = len(df_all_trades[df_all_trades['pnl_points'] < 0])
            c_win_rate = (c_wins / c_total) * 100
            c_pnl = df_all_trades['pnl_points'].sum()
            cg_prof = df_all_trades[df_all_trades['pnl_points'] > 0]['pnl_points'].sum()
            cg_loss = abs(df_all_trades[df_all_trades['pnl_points'] < 0]['pnl_points'].sum())
            c_pf = (cg_prof / cg_loss) if cg_loss > 0 else float('inf')
            c_stats = {'total_trades': c_total, 'win_count': c_wins, 'loss_count': c_losses, 'win_rate': c_win_rate, 'pnl': c_pnl, 'profit_factor': c_pf}
            
            yearly_report_data.append({'yearly': y_stats, 'cumulative': c_stats})
            send_yearly_progress_email(current_processing_year, y_stats, c_stats)
            
    # 輸出至 JSON 與 CSV 作為 GitHub Artifact 雲端暫存
    try:
        with open('backtest_yearly_results.json', 'w', encoding='utf-8') as f:
            json.dump(yearly_report_data, f, ensure_ascii=False, indent=2)
        if trades:
            pd.DataFrame(trades).to_csv('backtest_trades.csv', index=False, encoding='utf-8-sig')
        print("💾 回測結果 JSON 與 CSV 明細已成功寫入 GitHub Artifact 暫存檔案。")
    except Exception as e:
        print(f"⚠️ 寫入 Artifact 暫存檔失敗: {e}")
        
    return trades, yearly_report_data

def evaluate_performance(trades, label="測試報告"):
    """
    計算並呈現 10 年回測績效報告
    """
    print("\n" + "=" * 65)
    print(f"  🏆 10年期 PRZ 策略歷史回測績效報告【{label}】")
    print("=" * 65)
    
    if not trades:
        print("  ⚠️ 回測期間內未觸發任何符合條件之交易訊號。")
        print("=" * 65)
        return
        
    df_trades = pd.DataFrame(trades)
    total_trades = len(df_trades)
    win_trades = df_trades[df_trades['pnl_points'] > 0]
    loss_trades = df_trades[df_trades['pnl_points'] < 0]
    
    win_count = len(win_trades)
    loss_count = len(loss_trades)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0.0
    
    total_pnl = df_trades['pnl_points'].sum()
    gross_profit = win_trades['pnl_points'].sum() if not win_trades.empty else 0.0
    gross_loss = abs(loss_trades['pnl_points'].sum()) if not loss_trades.empty else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    
    df_trades['cum_pnl'] = df_trades['pnl_points'].cumsum()
    cum_max = df_trades['cum_pnl'].cummax()
    drawdown = cum_max - df_trades['cum_pnl']
    max_drawdown = drawdown.max()
    
    print(f"  📊 總交易次數      : {total_trades} 次")
    print(f"  🟢 獲利勝場      : {win_count} 次")
    print(f"  🔴 虧損敗場      : {loss_count} 次")
    print(f"  ⭐ 策略整體勝率   : {win_rate:.2f} %")
    print("--------------------------------------------------")
    print(f"  💰 累積總淨盈虧   : {total_pnl:+,.0f} 點")
    print(f"  📈 總獲利點數     : +{gross_profit:,.0f} 點")
    print(f"  📉 總虧損點數     : -{gross_loss:,.0f} 點")
    print(f"  ⚖️ 獲利因子(PF)  : {profit_factor:.2f}")
    print(f"  ⚠️ 最大回撤(MDD)  : {max_drawdown:,.0f} 點")
    print("=" * 65)

def main():
    tracker = StepErrorTracker(max_allowed_errors=3)
    
    print("=" * 65)
    print("  🚀 開始執行 10年期 (2016-2026) PRZ 策略遞迴歷史回測...")
    print("  📧 當每一年完成時，自動發送逐年勝率與累計勝率 Email 通報")
    print("  ☁️ 回測產出檔將自動上傳至 GitHub Actions Cloud Artifact 暫存")
    print("=" * 65)
    
    df_10y = fetch_10y_historical_data(tracker)
    if df_10y is None:
        print("❌ 無法取得 10 年歷史數據，回測中斷。")
        return
        
    trades_high_conf, yearly_report = run_backtest(df_10y, tracker, mode=3, high_confidence_only=True, max_holding_days=10)
    evaluate_performance(trades_high_conf, label="🔥高信心水準超級共振門檻 (逐年與累計勝率通報)")

if __name__ == '__main__':
    main()
