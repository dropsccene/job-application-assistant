"""report 日报测试（8/5 修复：按天统计 + 快照增量 + 回复率分母修正）。"""
import json
from datetime import datetime, timedelta, timezone

from boss_zhipin.report import generate_report


def _iso(days_ago: int, hour: int = 2) -> str:
    """UTC 时间戳字符串：02:00 UTC = 10:00 本地，保证与本地同一天。"""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return f"{dt:%Y-%m-%d}T{hour:02d}:00:00+00:00"


def _letter(ts, company, sent=True, validation_ok=True):
    return json.dumps({
        "ts": ts,
        "validation_ok": validation_ok,
        "sent": sent,
        "job_description": f"Python 后端\n{company} · 招聘者\n其他描述",
    }, ensure_ascii=False)


def test_generate_report_daily_and_delta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()

    # letters：今天 2 条（1 发 1 未发）+ 前天 1 条（已发）→ 当天应只算 2/1
    (logs / "letters.jsonl").write_text("\n".join([
        _letter(_iso(0), "今日公司A"),
        _letter(_iso(0), "今日公司B", sent=False),
        _letter(_iso(2), "旧日公司C"),
    ]) + "\n", encoding="utf-8")

    # llm：今天 1 次 + 前天 1 次 → 当天只算 1 次
    (logs / "llm_calls.jsonl").write_text("\n".join([
        json.dumps({"ts": _iso(0), "usage": {"prompt_tokens": 100, "completion_tokens": 50}}),
        json.dumps({"ts": _iso(2), "usage": {"prompt_tokens": 100, "completion_tokens": 50}}),
    ]) + "\n", encoding="utf-8")

    # 历史：上次快照已有 1 条回复；本次快照同条仍在 + 新增 1 条拒绝 + 送达/已读
    (logs / "inbox_history.jsonl").write_text("\n".join([
        json.dumps({"checked_at": "2026-08-04T08:00:00", "conversations": [
            {"company": "旧回复公司", "status": "已回复(积极)", "last_msg": "方便聊聊"},
        ]}),
        json.dumps({"checked_at": "2026-08-05T08:00:00", "conversations": [
            {"company": "旧回复公司", "status": "已回复(积极)", "last_msg": "方便聊聊"},
            {"company": "新回复公司", "status": "已回复(拒绝)", "last_msg": "不太合适"},
            {"company": "送达公司", "status": "送达", "last_msg": "[送达]"},
            {"company": "已读公司", "status": "已读", "last_msg": "[已读]"},
        ]}),
    ]) + "\n", encoding="utf-8")

    report = generate_report()

    # 当天统计：旧日志不算进来
    assert "| 生成招呼语 | 2 条 |" in report
    assert "| 实际发送 | 1 条 |" in report
    assert "| 累计发送 | 2 条 |" in report
    assert "| LLM 调用 | 1 次 |" in report
    assert "¥0.0002" in report  # 100/1M*1 + 50/1M*2
    # 已发公司是今天的，旧公司的名字不出现在报告里
    assert "今日公司A" in report
    assert "旧日公司C" not in report

    # HR 反馈三桶 + 增量
    assert "| 送达（HR 未打开） | 1 条 |" in report
    assert "| 已读（看了没回） | 1 条 |" in report
    assert "| 已回复 | 2 条（积极 1 / 拒绝 1 / 其他 0） |" in report
    # 新增回复只列本次快照新出现的，旧账不算
    assert "新回复公司" in report
    assert "旧回复公司" not in report.split("新增回复")[0]
    # 回复率 = 新增回复 1 / 当天发送 1
    assert "| 回复率（新增回复/当天发送） | 100% |" in report


def test_generate_report_no_data(tmp_path, monkeypatch):
    """没有日志/没有历史 → 不崩，回复率显示占位。"""
    monkeypatch.chdir(tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "letters.jsonl").write_text("", encoding="utf-8")
    (logs / "llm_calls.jsonl").write_text("", encoding="utf-8")

    report = generate_report()

    assert "| 实际发送 | 0 条 |" in report
    assert "| 送达（HR 未打开） | 0 条 |" in report
    assert "| 回复率（新增回复/当天发送） | — |" in report
