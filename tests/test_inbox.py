"""inbox 状态分类 + 历史快照测试（8/5 修复：送达/已读/已回复三桶）。"""
import json

from boss_zhipin.inbox import _classify, save_inbox_log, load_inbox_history


def test_classify_markers():
    """BOSS DOM 自带的状态标记 → 对应桶。"""
    assert _classify("[送达]") == "送达"
    assert _classify("[已读]") == "已读"
    assert _classify("[未读]") == "未读"
    assert _classify("") == "未读"


def test_classify_replies():
    """HR 回复正文 → 拒绝/积极/普通三档。"""
    assert _classify("[祈祷] 不好意思，不太合适哦") == "已回复(拒绝)"
    assert _classify("感谢投递，但不太符合我们的要求") == "已回复(拒绝)"
    assert _classify("方便聊聊吗？") == "已回复(积极)"
    assert _classify("你好，可以约个时间聊聊") == "已回复(积极)"
    assert _classify("好的") == "已回复"


def test_classify_marker_with_text():
    """标记和正文粘在一起时，以正文为准（"已读"后面跟了回复也是回复）。"""
    assert _classify("[已读] 方便聊聊吗") == "已回复(积极)"


def test_save_inbox_log_seeds_history(tmp_path, monkeypatch):
    """首次保存：把修复前遗留的旧快照作为第一条历史，之后追加本次快照。"""
    monkeypatch.chdir(tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "inbox_status.json").write_text(
        json.dumps({
            "checked_at": "2026-08-05T00:00:00",
            "conversations": [{"company": "旧公司", "status": "已读", "last_msg": "[送达]"}],
        }),
        encoding="utf-8")

    save_inbox_log([{"company": "新公司", "status": "送达", "last_msg": "[送达]"}])

    history = load_inbox_history()
    assert len(history) == 2
    assert history[0]["conversations"][0]["company"] == "旧公司"
    assert history[1]["conversations"][0]["company"] == "新公司"

    # 快照文件本身是最新的（兼容旧读取路径）
    status = json.loads((logs / "inbox_status.json").read_text(encoding="utf-8"))
    assert status["conversations"][0]["company"] == "新公司"


def test_load_inbox_history_missing_file(tmp_path, monkeypatch):
    """没有历史文件 → 返回空列表，不抛异常。"""
    monkeypatch.chdir(tmp_path)
    assert load_inbox_history() == []
