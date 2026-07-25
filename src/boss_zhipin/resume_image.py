"""简历图片 + Demo 动图——直接使用用户准备好的文件。"""
from pathlib import Path
import shutil

_USER_JPEG = Path.home() / "Desktop" / "面试" / "JD" / "袁仕杰_简历_Python后端AI方向.jpeg"
_DEMO_GIF = Path("resume") / "demo_rag_stream.gif"


def get_resume_image() -> Path | None:
    """获取简历图片路径。复制到项目目录供上传。"""
    if not _USER_JPEG.exists():
        return None
    output = Path("resume") / "resume_card.jpeg"
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
