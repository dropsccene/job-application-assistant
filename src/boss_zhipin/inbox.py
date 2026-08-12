"""BOSS直聘聊天列表监控——解析 body text 提取对话状态

BOSS 聊天列表的 DOM 自带状态标记，``document.body.innerText`` 里能直接看到
``[送达]`` / ``[已读]`` / ``[未读]`` 字样：

- ``[送达]``：消息送达但对方**还没打开** → 归为「送达」（真正的"未触达"，日报里
  最要紧的数字）
- ``[已读]``：对方打开过但没回复 → 「已读」
- 其余（对方发来的正文）→ 「已回复(积极/拒绝/其他)」

8/5 修复前：所有 ``[送达]`` 被归进"已读"，让已读数虚胖、日报里看不到真实送达
率；且每次检查只覆盖 ``inbox_status.json`` 单张快照，日报没有历史可比，"新增
回复"无从谈起。修复后每次快照同时追加进 ``logs/inbox_history.jsonl``，日报
据此算增量。
"""
import json
import asyncio
import re
from pathlib import Path
from datetime import datetime

DELIVERED_MARKERS = ("[送达]",)
READ_MARKERS = ("[已读]",)
UNREAD_MARKERS = ("[未读]",)

REJECT_WORDS = ("遗憾", "不合适", "不太合适", "不匹配", "不太符合", "无法", "不通过", "不考虑", "暂停", "招满", "已满")
POSITIVE_WORDS = ("方便聊聊", "约个时间", "面聊", "感兴趣", "来面试", "电话", "加微信", "方便的话")


def _classify(last_msg: str) -> str:
    """根据 BOSS 聊天列表最后一条消息判断状态。

    优先剥离 [送达]/[已读]/[未读] 标记：标记之外还有实质内容（≥2 字）就当作
    HR 回复正文分类；纯标记行才归入送达/已读/未读桶。
    """
    msg = (last_msg or "").strip()
    marker = ""
    for m in DELIVERED_MARKERS + READ_MARKERS + UNREAD_MARKERS:
        if m in msg:
            marker = m
            msg = msg.replace(m, "").strip()
            break

    if len(msg) >= 2:
        if any(w in msg for w in REJECT_WORDS):
            return "已回复(拒绝)"
        if any(w in msg for w in POSITIVE_WORDS):
            return "已回复(积极)"
        return "已回复"

    if marker in DELIVERED_MARKERS:
        return "送达"
    if marker in READ_MARKERS:
        return "已读"
    return "未读"


async def check_inbox(tab) -> list[dict]:
    """导航到 BOSS 聊天页，解析 body text 提取最近对话状态。"""
    results = []

    try:
        await tab.get("https://www.zhipin.com/web/geek/chat")
        await asyncio.sleep(4)

        body = await tab.evaluate("document.body.innerText")
        if not body:
            return results

        lines = [l.strip() for l in str(body).split("\n") if l.strip()]

        # 解析：每个对话块以 HR 信息行开始（含"招聘"/"经理"/"HR"/"主管"/"顾问"）
        i = 0
        while i < len(lines):
            line = lines[i]
            # HR 行特征：包含职位标识词
            hr_keywords = ("招聘", "经理", "HR", "主管", "顾问", "人事", "总监", "老板")
            if any(k in line for k in hr_keywords) and len(line) < 50:
                company = line[:40]

                # 找下一条消息内容（跳过时间戳和数字）
                last_msg = ""
                j = i + 1
                while j < len(lines) and j < i + 5:
                    next_line = lines[j]
                    # 时间格式跳过
                    if re.match(r"^\d{1,2}:\d{2}$", next_line):
                        j += 1
                        continue
                    # 纯数字跳过
                    if re.match(r"^\d+$", next_line):
                        j += 1
                        continue
                    # 附件名跳过
                    if next_line.endswith((".pdf", ".jpg", ".png", ".doc", ".docx")):
                        j += 1
                        continue
                    # 简历相关跳过
                    if "简历" in next_line and len(next_line) < 30:
                        j += 1
                        continue

                    last_msg = next_line[:120]
                    break

                results.append({
                    "company": company,
                    "status": _classify(last_msg),
                    "last_msg": last_msg,
                })

            i += 1

    except Exception as e:
        results.append({
            "company": "错误",
            "status": f"抓取失败: {e}",
            "last_msg": "",
        })

    return results


def save_inbox_log(results: list[dict]) -> Path:
    """保存本次快照，并追加进历史（inbox_history.jsonl）供日报算增量。

    首次写入时，如果已有修复前遗留的 inbox_status.json，把它作为第一条历史
    带进去——日报从第二天起就有"上次快照"可以对比新增回复。
    """
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    status_file = log_dir / "inbox_status.json"
    history_file = log_dir / "inbox_history.jsonl"

    # 1) 历史里还没有快照、但存在旧版状态文件 → 先把它作为第一条历史
    #    （必须在覆盖 status_file 之前读）
    if not history_file.exists() and status_file.exists():
        try:
            old = json.loads(status_file.read_text(encoding="utf-8"))
            if old.get("conversations"):
                history_file.write_text(
                    json.dumps(old, ensure_ascii=False) + "\n", encoding="utf-8")
        except (json.JSONDecodeError, KeyError):
            pass

    data = {"checked_at": datetime.now().isoformat(), "conversations": results}

    # 2) 快照（覆盖，兼容 GUI / inbox_summary 的旧读取路径）
    status_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) 历史（追加，日报算增量用；跟 letters.jsonl 一样只增不裁）
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

    return status_file


def load_inbox_log() -> list[dict]:
    log_file = Path("logs") / "inbox_status.json"
    if not log_file.exists():
        return []
    try:
        data = json.loads(log_file.read_text(encoding="utf-8"))
        return data.get("conversations", [])
    except (json.JSONDecodeError, KeyError):
        return []


def load_inbox_history() -> list[dict]:
    """读历史快照（按时间顺序）。文件缺失/损坏返回 []。"""
    history_file = Path("logs") / "inbox_history.jsonl"
    snapshots = []
    if history_file.exists():
        for line in history_file.read_text(encoding="utf-8").strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                snapshots.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return snapshots


def inbox_summary() -> str:
    convs = load_inbox_log()
    if not convs:
        return ""

    total = len(convs)
    delivered = sum(1 for c in convs if c.get("status") == "送达")
    read = sum(1 for c in convs if c.get("status") == "已读")
    replied = sum(1 for c in convs if str(c.get("status", "")).startswith("已回复"))
    positive = sum(1 for c in convs if "积极" in c.get("status", ""))
    rejected = sum(1 for c in convs if "拒绝" in c.get("status", ""))

    lines = [
        f"| 聊天监控 | {total} 个对话 |",
        f"| 送达（未打开） | {delivered} 个 |",
        f"| 已读（看了没回） | {read} 个 |",
        f"| 已回复 | {replied} 个（积极 {positive} / 拒绝 {rejected}） |",
    ]

    if positive > 0:
        names = [c["company"] for c in convs if "积极" in c.get("status", "")]
        lines.append(f"| 积极回复 | {', '.join(names[:5])} |")

    return "\n".join(lines)
