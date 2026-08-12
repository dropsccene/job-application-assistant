"""简历图片 + Demo 动图——直接使用用户准备好的文件。"""
from __future__ import annotations

import os
from pathlib import Path
import shutil

# 简历图片路径：优先用 BOSS_RESUME_IMAGE env 覆盖（发布版可配），
# 没设置时回退到本机默认路径。
_default_user_jpeg = os.environ.get("BOSS_RESUME_IMAGE", "").strip()
if _default_user_jpeg:
    _USER_JPEG = Path(_default_user_jpeg).expanduser()
else:
    _USER_JPEG = Path.home() / "Desktop" / "面试" / "JD" / "袁仕杰_简历_Python后端AI方向.jpeg"
_RESUME_CARD = Path("resume") / "resume_card.jpeg"
_DEMO_GIF = Path("resume") / "demo_rag_stream.gif"


def get_resume_image() -> Path | None:
    """获取简历图片路径。复制到项目目录供上传。"""
    if not _USER_JPEG.exists():
        return None
    output = _RESUME_CARD
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists() or output.stat().st_mtime < _USER_JPEG.stat().st_mtime:
        shutil.copy2(_USER_JPEG, output)
    return output


def get_demo_gif() -> Path | None:
    """获取 Demo 动图路径。

    Demo GIF 展示 RAG 流式问答效果，比静态简历更有说服力。
    优先用动图，不存在时回退到简历图片。
    """
    if _DEMO_GIF.exists():
        return _DEMO_GIF
    return get_resume_image()


def resolve_chat_attachments() -> list[Path]:
    """按环境变量决定给 HR 发哪些附件，返回空列表表示不发送。

    - ``BOSS_SEND_RESUME_IMAGE=1``：发简历图片（resume_card.jpeg）
    - ``BOSS_SEND_DEMO_GIF=1``：发 Demo 动图（展示 RAG 流式效果）
    - 两个都设：先简历图片、再 Demo 动图——HR 第一眼看到简历，
      然后看到能点的 Demo 效果
    - 都没设：不发附件
    """
    send_resume = os.getenv("BOSS_SEND_RESUME_IMAGE", "").strip() == "1"
    send_demo = os.getenv("BOSS_SEND_DEMO_GIF", "").strip() == "1"
    attachments: list[Path] = []
    if send_resume:
        img = get_resume_image()
        if img:
            attachments.append(img)
    if send_demo:
        gif = get_demo_gif()
        # 动图缺失时 get_demo_gif 会回退简历图——已在列表里就不重复发
        if gif and (not attachments or gif != attachments[0]):
            attachments.append(gif)
    return attachments
