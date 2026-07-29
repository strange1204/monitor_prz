"""
PRZ 系統 Email 通知模組 (Gmail SMTP)
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText

sys.stdout.reconfigure(encoding='utf-8')

# SMTP / Email 設定
GMAIL_SENDER = os.environ.get("GMAIL_SENDER", "strange751204@gmail.com")
GMAIL_RECEIVER = os.environ.get("GMAIL_RECEIVER", "brian555878@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "qaua nssw vztv ytbk")

def send_email_report(subject: str, body: str) -> bool:
    """
    透過 Gmail SMTP 發送通知郵件
    
    Args:
        subject (str): 主旨
        body (str): 內容
        
    Returns:
        bool: 發送成功與否
    """
    if not GMAIL_APP_PASSWORD:
        print("⚠️ 未設定 Gmail App Password，取消發信。")
        return False
        
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = GMAIL_SENDER
        msg['To'] = GMAIL_RECEIVER
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD.replace(" ", ""))
        server.sendmail(GMAIL_SENDER, [GMAIL_RECEIVER], msg.as_string())
        server.quit()
        print(f"✅ SUCCESS: Email 已成功寄送至 {GMAIL_RECEIVER}")
        return True
    except Exception as e:
        print(f"⚠️ SMTP 發信失敗: {e}")
        return False

if __name__ == '__main__':
    test_subject = "【測試通知】台指期 PRZ 諧波分析系統"
    test_body = "這是一封來自台指期 PRZ 分析系統的測試郵件。"
    send_email_report(test_subject, test_body)
