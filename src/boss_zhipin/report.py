"""每日投递报告生成器。

8/5 修复（此前报告里的三个数字错误）：
1. **累计当"当天"**：letters.jsonl / llm_calls.jsonl 是终身日志，旧代码不按日期
   过滤，导致"生成/发送"永远是累计值、"已发公司"永远是历史上前 10 家（7/21 起
   一个字没变过）。现在按本地日期过滤，报告里是真正的"当天"。
2. **快照当"漏斗"**：inbox_status.json 只是聊天页某一次检查的快照（每次覆盖），
   旧代码直接拿它当累计漏斗，7/29/8/01/8/03 才会出现一模一样的回复名单。现在读
   ``logs/inbox_history.jsonl`` 历史快照，算"较上次快照新增"的回复。
3. **时间基混除**：旧回复率 = 快照回复数 / 终身累计发送数，分母天天涨、分子是
   单张快照，比率机械性跌向 0。现在回复率 = 新增回复 / 当天发送。

修复后"HR 反馈"给三桶真实数据（来自 BOSS 聊天列表自带的 [送达]/[已读] 标记）：
送达（HR 未打开）→ 已读（看了没回）→ 已回复。
"""
import json
import os
from pathlib import Path
from datetime import datetime, date

from boss_zhipin.inbox import load_inbox_history


def _local_date(ts: str) -> date | None:
    """ISO 时间戳（含时区）→ 本地日期。解析失败返回 None。"""
    try:
        return datetime.fromisoformat(ts).astimezone().date()
    except (ValueError, TypeError):
        return None


def _company_from_jd(jd: str) -> str:
    """从 JD 原文里捞公司名（跟历史实现一致：找带"·"的 HR 行，取"·"前的部分）。"""
    for ln in jd.split("\n"):
        if "·" in ln and any(k in ln for k in ("招聘", "经理", "主管", "HR", "总监")):
            company = ln.split("·")[0].strip()
            if len(company) > 20:
                company = ""
            return company
    return "未知"


def generate_report() -> str:
    """从 letters.jsonl + llm_calls.jsonl + inbox_history.jsonl 生成每日投递报告"""
    log_dir = Path("logs")
    letters_log = log_dir / "letters.jsonl"
    llm_log = log_dir / "llm_calls.jsonl"

    today = date.today()

    # ---- 统计 letters（当天；累计只作参考）----
    total_generated = 0
    total_sent = 0
    companies_sent = []
    cum_generated = 0
    cum_sent = 0

    if letters_log.exists():
        with open(letters_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if not e.get("validation_ok"):
                        continue
                    cum_generated += 1
                    is_today = _local_date(e.get("ts", "")) == today
                    if is_today:
                        total_generated += 1
                    if e.get("sent"):
                        cum_sent += 1
                        if is_today:
                            total_sent += 1
                            companies_sent.append(_company_from_jd(e.get("job_description", "")))
                except json.JSONDecodeError:
                    continue

    # ---- 统计 LLM 调用（当天）----
    total_llm_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0

    if llm_log.exists():
        with open(llm_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if _local_date(e.get("ts", "")) != today:
                        continue
                    total_llm_calls += 1
                    usage = e.get("usage", {})
                    total_input_tokens += usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                    total_output_tokens += usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
                except json.JSONDecodeError:
                    continue

    cost_input = total_input_tokens / 1_000_000 * 1
    cost_output = total_output_tokens / 1_000_000 * 2
    total_cost = cost_input + cost_output

    # ---- 统计 HR 回复（较上次快照的增量）----
    delivered = 0
    read = 0
    replied_positive = 0
    replied_rejected = 0
    replied_other = 0
    new_replied = []

    snapshots = load_inbox_history()
    if snapshots:
        prev_replied = set()
        # 上次快照里已回复的公司 → 本次"新增"回复靠它排除旧账。
        # 只有一条快照时 prev 为空，首次报告会把当前回复都算作新增（可接受）。
        if len(snapshots) >= 2:
            for c in snapshots[-2].get("conversations", []):
                if str(c.get("status", "")).startswith("已回复"):
                    prev_replied.add(c.get("company", ""))

        for c in snapshots[-1].get("conversations", []):
            status = str(c.get("status", ""))
            if status == "送达":
                delivered += 1
            elif status == "已读":
                read += 1
            elif status.startswith("已回复"):
                if "积极" in status:
                    replied_positive += 1
                elif "拒绝" in status:
                    replied_rejected += 1
                else:
                    replied_other += 1
                company = c.get("company", "")
                if company not in prev_replied:
                    new_replied.append(company)

    replied_total = replied_positive + replied_rejected + replied_other

    # ---- 生成报告 ----
    lines = [
        "",
        f"## 📊 投递报告 — {today.isoformat()}",
        "",
        "### 本轮投递（当天）",
        "",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 浏览岗位 | — |",
        f"| 生成招呼语 | {total_generated} 条 |",
        f"| 实际发送 | {total_sent} 条 |",
        f"| 累计发送 | {cum_sent} 条 |",
        f"| LLM 调用 | {total_llm_calls} 次 |",
        f"| 预估费用 | ¥{total_cost:.4f} |",
    ]
    if companies_sent:
        lines.append(f"| 已发公司 | {', '.join(companies_sent[:10])} |")

    lines += [
        "",
        "### HR 反馈（较上次快照）",
        "",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 送达（HR 未打开） | {delivered} 条 |",
        f"| 已读（看了没回） | {read} 条 |",
        f"| 已回复 | {replied_total} 条（积极 {replied_positive} / 拒绝 {replied_rejected} / 其他 {replied_other}） |",
    ]
    if new_replied:
        lines.append(f"| 新增回复 | {len(new_replied)} 条：{', '.join(new_replied[:10])} |")

    if total_sent > 0:
        rate = f"{len(new_replied) / total_sent * 100:.0f}%"
    else:
        rate = "—"
    lines.append(f"| 回复率（新增回复/当天发送） | {rate} |")

    lines.append("")

    return "\n".join(lines)


def append_report_to_tracking(report: str) -> None:
    """将报告追加到投递记录.md末尾"""
    default_tracking = Path.home() / "Desktop" / "面试" / "投递记录.md"
    tracking_file = Path(os.environ.get("BOSS_TRACKING_FILE", "")).expanduser() \
        if os.environ.get("BOSS_TRACKING_FILE", "").strip() else default_tracking
    if not tracking_file.exists():
        return

    content = tracking_file.read_text(encoding="utf-8")

    # 避免重复追加同一天的报告
    today_iso = datetime.now().strftime("%Y-%m-%d")
    if f"投递报告 — {today_iso}" in content:
        return

    tracking_file.write_text(content + report + "\n", encoding="utf-8")
    try:
        print(report)
    except UnicodeEncodeError:
        # GBK 控制台打不出 emoji——报告已写入文件，控制台打印只是顺带
        pass
