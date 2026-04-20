#!/usr/bin/env python3
"""wiki 周报 - 每周一推送待审核草稿到飞书"""

import json, subprocess, os, sys, re
from datetime import date
from pathlib import Path

WIKI_ROOT = os.environ.get("WIKI_ROOT", "/root/chris/wiki")

APP_ID = "cli_a905e78109f89bb5"
APP_SECRET = "JFaisf4kq9RLJO8jmgzXDcjOHQ7sShNA"
USER_OPEN_ID = "ou_f1724f7ff881ac04a8b5af02cec7833b"

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)

def get_pending_drafts():
    """Run wiki promote to get pending drafts."""
    env = os.environ.copy()
    env["WIKI_ROOT"] = WIKI_ROOT
    result = subprocess.run(
        ["wiki", "promote"],
        capture_output=True, text=True, timeout=30,
        env=env
    )
    return result.stdout

def get_compile_status():
    """Quick status check."""
    env = os.environ.copy()
    env["WIKI_ROOT"] = WIKI_ROOT
    result = subprocess.run(
        ["wiki", "status"],
        capture_output=True, text=True, timeout=30,
        env=env
    )
    return result.stdout

def get_feishu_token():
    resp = run(["curl", "-s", "-X", "POST",
         "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET})])
    data = json.loads(resp.stdout)
    token = data.get("tenant_access_token", "")
    if not token:
        print(f"获取token失败: {resp.stdout}", file=sys.stderr)
        sys.exit(1)
    return token

def send_feishu_message(token, text):
    content_str = json.dumps({"text": text}, ensure_ascii=False)
    body = {
        "receive_id": USER_OPEN_ID,
        "msg_type": "text",
        "content": content_str
    }
    body_json = json.dumps(body, ensure_ascii=False)
    resp = run(["curl", "-s", "-X", "POST",
         "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
         "-H", f"Authorization: Bearer {token}",
         "-H", "Content-Type: application/json",
         "-d", body_json])
    data = json.loads(resp.stdout)
    code = data.get("code", 999)
    if code == 0:
        print(f"发送成功: {data.get('data', {}).get('message_id')}")
    else:
        print(f"发送失败 [{code}]: {data.get('msg')}", file=sys.stderr)
        print(f"完整响应: {resp.stdout}", file=sys.stderr)

def main():
    pending = get_pending_drafts()
    status = get_compile_status()

    # Check if there are actually pending drafts
    has_pending = "Pending" in pending or "pending" in pending.lower()
    has_drafts = any(line.strip() for line in pending.split("\n")
                     if line.strip() and "─" not in line and "┃" not in line
                     and "To promote" not in line and "To reject" not in line
                     and "To promote all" not in line
                     and "Pending Compiled" not in line)

    today = date.today().isoformat()

    if not has_drafts:
        msg = f"""📚 Wiki 周报 {today}
暂无待审核草稿，知识库运行正常。
回复 #ask 查询知识库，#wiki 采集新素材。"""
    else:
        # Count data rows: lines that start with │ and contain a row number
        count = 0
        for line in pending.split("\n"):
            stripped = line.strip()
            if stripped.startswith("│") and re.match(r"│\s*\d", stripped):
                count += 1

        msg = f"""📚 Wiki 周报 {today}
有 {count} 条草稿待审核：

{pending.strip()}

操作方式（在飞书回复即可）：
- 「wiki promote <标题>」晋升入库
- 「wiki promote all」全部晋升
- 「wiki reject <标题>」拒绝
- 或 SSH 运行 wiki promote 命令"""

    token = get_feishu_token()
    send_feishu_message(token, msg)

if __name__ == "__main__":
    main()
