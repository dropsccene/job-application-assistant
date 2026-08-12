"""tests for boss_zhipin.resume_image.resolve_chat_attachments.

附件选择逻辑的开关矩阵：
- 都没设 → 不发
- BOSS_SEND_RESUME_IMAGE=1 → 发简历图片
- BOSS_SEND_DEMO_GIF=1 → 发 Demo 动图
- 两个都设 → 简历图片在前、Demo 动图在后（都发）
- Demo 动图缺失 → 回退简历图片（不重复发）
- 源简历图片缺失 → 不发送
"""

import pytest

import boss_zhipin.resume_image as rm


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """每个用例都从干净的 env 出发。"""
    monkeypatch.delenv("BOSS_SEND_RESUME_IMAGE", raising=False)
    monkeypatch.delenv("BOSS_SEND_DEMO_GIF", raising=False)


def _fake_src(monkeypatch, tmp_path):
    """把简历源文件 / 输出落点 / 动图全部指到 tmp，避免碰真实文件。"""
    src = tmp_path / "my_resume.jpeg"
    src.write_bytes(b"fake-jpeg")
    monkeypatch.setattr(rm, "_USER_JPEG", src)
    monkeypatch.setattr(rm, "_RESUME_CARD", tmp_path / "resume_card.jpeg")
    monkeypatch.setattr(rm, "_DEMO_GIF", tmp_path / "demo_rag_stream.gif")
    return src


def test_no_env_returns_empty(monkeypatch, tmp_path):
    _fake_src(monkeypatch, tmp_path)
    assert rm.resolve_chat_attachments() == []


def test_resume_image_flag_returns_resume_card(monkeypatch, tmp_path):
    _fake_src(monkeypatch, tmp_path)
    monkeypatch.setenv("BOSS_SEND_RESUME_IMAGE", "1")
    result = rm.resolve_chat_attachments()
    assert [p.name for p in result] == ["resume_card.jpeg"]


def test_resume_image_flag_copies_from_user_jpeg(monkeypatch, tmp_path):
    """简历图片开关：源文件被复制到 resume/ 落点，内容一致。"""
    _fake_src(monkeypatch, tmp_path)
    monkeypatch.setenv("BOSS_SEND_RESUME_IMAGE", "1")
    result = rm.resolve_chat_attachments()
    assert result[0].read_bytes() == b"fake-jpeg"


def test_demo_gif_flag_returns_gif(monkeypatch, tmp_path):
    _fake_src(monkeypatch, tmp_path)
    gif = tmp_path / "demo_rag_stream.gif"
    gif.write_bytes(b"fake-gif")
    monkeypatch.setenv("BOSS_SEND_DEMO_GIF", "1")
    result = rm.resolve_chat_attachments()
    assert [p.name for p in result] == ["demo_rag_stream.gif"]


def test_both_flags_send_both_resume_first(monkeypatch, tmp_path):
    """两个开关都开：简历图片在前、Demo 动图在后，两张都发。"""
    _fake_src(monkeypatch, tmp_path)
    gif = tmp_path / "demo_rag_stream.gif"
    gif.write_bytes(b"fake-gif")
    monkeypatch.setenv("BOSS_SEND_RESUME_IMAGE", "1")
    monkeypatch.setenv("BOSS_SEND_DEMO_GIF", "1")
    result = rm.resolve_chat_attachments()
    assert [p.name for p in result] == ["resume_card.jpeg", "demo_rag_stream.gif"]


def test_demo_gif_flag_falls_back_to_resume(monkeypatch, tmp_path):
    """动图缺失时回退简历图片。"""
    _fake_src(monkeypatch, tmp_path)  # 不创建 gif 文件
    monkeypatch.setenv("BOSS_SEND_DEMO_GIF", "1")
    result = rm.resolve_chat_attachments()
    assert [p.name for p in result] == ["resume_card.jpeg"]


def test_both_flags_gif_missing_no_duplicate(monkeypatch, tmp_path):
    """都开但动图缺失：只发一张简历图，不重复。"""
    _fake_src(monkeypatch, tmp_path)  # 不创建 gif 文件
    monkeypatch.setenv("BOSS_SEND_RESUME_IMAGE", "1")
    monkeypatch.setenv("BOSS_SEND_DEMO_GIF", "1")
    result = rm.resolve_chat_attachments()
    assert [p.name for p in result] == ["resume_card.jpeg"]


def test_resume_flag_missing_source_returns_empty(monkeypatch, tmp_path):
    """源简历图片不存在 → 空列表（不发空附件）。"""
    src = tmp_path / "missing.jpeg"  # 不创建文件
    monkeypatch.setattr(rm, "_USER_JPEG", src)
    monkeypatch.setattr(rm, "_RESUME_CARD", tmp_path / "resume_card.jpeg")
    monkeypatch.setattr(rm, "_DEMO_GIF", tmp_path / "demo_rag_stream.gif")
    monkeypatch.setenv("BOSS_SEND_RESUME_IMAGE", "1")
    assert rm.resolve_chat_attachments() == []
