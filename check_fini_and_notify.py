"""
外資現貨買賣超數據即時追蹤與 Email 自動通報腳本
當證交所/FinMind 公布今日三大法人現貨買賣超數據時，自動發送 Email 通知
"""

import sys
import os
import time
import json
import ssl
import datetime
import urllib.request
import urllib.parse
from notifier import send_email_report

# 設定標準輸出編碼為 UTF-8
sys.stdout.reconfigure(encoding='utf-8')

SSL_CONTEXT = ssl._create_unverified_context()
STATE_FILE = "C:\\monitor_PRZ\\last_notification_state.json"

def check_twse_openapi():
    """使用 FinMind API 查詢今日三大法人現貨買賣超數據"""
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    url = f'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockTotalInstitutionalInvestors&start_date={today_str}'
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            rows = data.get('data', [])
            if rows:
                return rows
    except Exception as e:
        print(f"  ⚠️ 查詢 FinMind API 發生異常: {e}")
    return None

def check_and_notify_fini():
    """檢查今日外資/三大法人現貨數據，若已公布且尚未通知，則發送 Email"""
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    
    # 讀取通知狀態檔
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except Exception:
            state = {}
            
    # 檢查今日是否已發送過通報
    if state.get('fini_notified_date') == today_str:
        return False
        
    rows = check_twse_openapi()
    if not rows:
        return False
        
    today_formatted = datetime.date.today().strftime('%Y年%m月%d日')
    
    fini_data = None
    trust_data = None
    dealer_self_data = None
    dealer_hedge_data = None
    total_data = None
    
    for row in rows:
        name = row.get('name', '')
        if name == 'Foreign_Investor':
            fini_data = row
        elif name == 'Investment_Trust':
            trust_data = row
        elif name == 'Dealer_self':
            dealer_self_data = row
        elif name == 'Dealer_Hedging':
            dealer_hedge_data = row
        elif name == 'total':
            total_data = row
            
    # 計算金額 (轉為億元)
    fini_buy = (fini_data['buy'] / 1e8) if fini_data else 0
    fini_sell = (fini_data['sell'] / 1e8) if fini_data else 0
    fini_net = fini_buy - fini_sell
    
    trust_net = ((trust_data['buy'] - trust_data['sell']) / 1e8) if trust_data else 0
    dealer_self_net = ((dealer_self_data['buy'] - dealer_self_data['sell']) / 1e8) if dealer_self_data else 0
    dealer_hedge_net = ((dealer_hedge_data['buy'] - dealer_hedge_data['sell']) / 1e8) if dealer_hedge_data else 0
    dealer_total_net = dealer_self_net + dealer_hedge_net
    
    total_net = ((total_data['buy'] - total_data['sell']) / 1e8) if total_data else 0
    
    fini_action = "買超" if fini_net >= 0 else "賣超"
    total_action = "買超" if total_net >= 0 else "賣超"

    subject = f"【台股三大法人盤後通報】{today_formatted} 外資現貨{fini_action} {abs(fini_net):.2f} 億元"
    
    content = f"""親愛的 Brian 您好：

📊【台股 {today_formatted} 三大法人現貨買賣超統計通報】📊
==================================================
⏰ 通報時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (台灣時間)
==================================================

🌐 1. 外資及陸資 (Foreign Investor)：
   • 買進金額：{fini_buy:,.2f} 億元
   • 賣出金額：{fini_sell:,.2f} 億元
   • ⭐ 買賣超金額：【外資 {fini_action} {abs(fini_net):,.2f} 億元】

🏛️ 2. 投信 (Investment Trust)：
   • 買賣超金額：【投信 {"買超" if trust_net>=0 else "賣超"} {abs(trust_net):,.2f} 億元】

💼 3. 自營商 (Dealer)：
   • 自營商 (自行買賣)：{"買超" if dealer_self_net>=0 else "賣超"} {abs(dealer_self_net):,.2f} 億元
   • 自營商 (避險)：{"買超" if dealer_hedge_net>=0 else "賣超"} {abs(dealer_hedge_net):,.2f} 億元
   • 小計買賣超：【自營商 {"買超" if dealer_total_net>=0 else "賣超"} {abs(dealer_total_net):,.2f} 億元】

==================================================
💰 三大法人現貨合計：【{total_action} {abs(total_net):,.2f} 億元】
==================================================

說明：本信件由 TWSE/FinMind 盤後資料庫自動偵測公布後第一時間發送。
"""

    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🎉 偵測到今日外資現貨買賣超數據已正式公布！發送 Email 通知...")
    success = send_email_report(subject, content)
    if success:
        state['fini_notified_date'] = today_str
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 寫入狀態檔失敗: {e}")
        print("✅ 今日外資買賣超 Email 通報發送完成並已登記！")
        return True
    return False

if __name__ == '__main__':
    check_and_notify_fini()
