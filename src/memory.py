"""长期记忆存储层：基于文件的持久化记忆系统。"""

import os
import sys
import tempfile


def _get_data_dir():
    """编译版使用 APPDATA，源码版使用本地目录。"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "DesktopPet")
    return os.path.dirname(os.path.abspath(__file__))


_DATA_DIR = _get_data_dir()


class MemoryStore:
    """管理 memory.md 文件的读写，支持条目级增删。"""

    MEMORY_FILE = os.path.join(_DATA_DIR, "memory.md")
    CHAR_LIMIT = 2200
    SEPARATOR = "\n§\n"

    # ============================== 读写 ==============================

    def load(self):
        """从文件读取所有记忆条目，返回字符串列表。"""
        if not os.path.exists(self.MEMORY_FILE):
            return []
        try:
            with open(self.MEMORY_FILE, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if not raw:
                return []
            return [e.strip() for e in raw.split(self.SEPARATOR) if e.strip()]
        except OSError:
            return []

    def save(self, entries):
        """原子写入：临时文件 → os.replace，防止写入中途崩溃。"""
        os.makedirs(os.path.dirname(self.MEMORY_FILE), exist_ok=True)
        content = self.SEPARATOR.join(entries)
        fd, tmp = tempfile.mkstemp(
            suffix=".tmp",
            prefix="memory_",
            dir=os.path.dirname(self.MEMORY_FILE),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(fd)
            os.replace(tmp, self.MEMORY_FILE)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ============================== 增删 ==============================

    def add(self, content):
        """添加一条记忆。返回 True 表示成功，False 表示重复或超限。"""
        content = content.strip()
        if not content:
            return False
        entries = self.load()
        if content in entries:
            return False
        total = sum(len(e) for e in entries) + len(content)
        sep_cost = len(self.SEPARATOR) * len(entries) if entries else 0
        if total + sep_cost > self.CHAR_LIMIT:
            return False
        entries.append(content)
        self.save(entries)
        return True

    def remove(self, content):
        """删除一条记忆。返回 True 表示找到并删除。"""
        content = content.strip()
        entries = self.load()
        if content not in entries:
            return False
        entries.remove(content)
        self.save(entries)
        return True

    # ============================== 格式化 ==============================

    def format_for_prompt(self):
        """格式化所有记忆为提示词片段，无记忆时返回空字符串。"""
        entries = self.load()
        if not entries:
            return ""
        lines = [f"- {e}" for e in entries]
        return "关于主人的记忆：\n" + "\n".join(lines)

    def usage_percent(self):
        """返回当前字符使用率百分比。"""
        entries = self.load()
        total = sum(len(e) for e in entries)
        if entries:
            total += len(self.SEPARATOR) * (len(entries) - 1)
        return round(total / self.CHAR_LIMIT * 100, 1) if self.CHAR_LIMIT else 0
