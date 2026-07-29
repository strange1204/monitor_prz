"""
GitHub 自動同步指令碼
將 C:\\monitor_PRZ\\ 下的原始碼推送到 https://github.com/strange1204/monitor_prz.git
"""

import subprocess
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

REPO_URL = "https://github.com/strange1204/monitor_prz.git"

def run_cmd(cmd, cwd="C:\\monitor_PRZ"):
    print(f"執行: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, encoding='utf-8', errors='ignore')
    if res.stdout:
        print(res.stdout)
    if res.stderr:
        print(res.stderr)
    return res.returncode == 0

def sync_to_github():
    print("🚀 開始同步程式至 GitHub (strange1204/monitor_prz)...")
    
    # 初始化 git
    if not os.path.exists("C:\\monitor_PRZ\\.git"):
        run_cmd(["git", "init"])
        run_cmd(["git", "branch", "-M", "main"])
        run_cmd(["git", "remote", "add", "origin", REPO_URL])
    
    # 檢查 remote
    run_cmd(["git", "remote", "set-url", "origin", REPO_URL])
    
    # 加入與提交
    run_cmd(["git", "add", "."])
    run_cmd(["git", "commit", "-m", "Update PRZ trading analysis system"])
    
    # 推送
    print("📤 正在推送至 GitHub (main)...")
    success = run_cmd(["git", "push", "-u", "origin", "main"])
    
    if success:
        print("✅ 同步成功！專案已更新至 https://github.com/strange1204/monitor_prz")
    else:
        print("⚠️ 自動推送遭遇身份驗證或權限問題，請確認 GitHub SSH/Token 設定後手動執行 git push -u origin main")

if __name__ == '__main__':
    sync_to_github()
