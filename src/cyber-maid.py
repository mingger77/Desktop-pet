import sys
import math
import random
import os
import json
import queue
from PySide6.QtWidgets import QApplication, QWidget, QMenu
from PySide6.QtCore import Qt, QTimer, QPoint, QRect
from PySide6.QtGui import QPainter, QPixmap

from dance import DanceMixin
from game import GameMixin
from chat import ChatMixin


class DesktopPet(QWidget, DanceMixin, GameMixin, ChatMixin):
    """桌面宠物 - 使用 PNG 精灵图，基于心情状态机驱动交互和动画。"""

    _TRIGGER_STATES = {
        "cute", "scaried", "apologize",
        "rock", "scissors", "paper",
        "win", "lose", "draw",
        "work"
    }

    def __init__(self):
        super().__init__()
        self._in_game = False
        self._dance_active = False
        self._dance_step = 0
        self._dance_poses = []
        self._dance_loops = 3
        self._player_choice = None
        self._chat_dialog = None
        self._chat_messages = []
        self._reply_queue = queue.Queue()
        self._identity = "maid"
        self._setup_window()
        self._load_config()
        self._load_all_images()
        self._init_state()
        self._setup_timers()
        self._setup_ui()

    # ============================== 初始化 ==============================

    def _setup_window(self):
        """配置无边框、透明、置顶窗口"""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(10, 10, 68, 48)

        self._dragging = False
        self._drag_offset = QPoint()
        self._press_pos = None

    def _load_all_images(self):
        """预加载 maid 和 catgirl 两组精灵图，换装时仅做指针交换。"""
        img_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
        self._all_images = {}

        if not os.path.isdir(img_dir):
            raise FileNotFoundError(f"图片目录不存在: {img_dir}")

        for identity in ("maid", "catgirl"):
            prefix = identity + "--"
            images = {}
            for fname in os.listdir(img_dir):
                if not fname.endswith(".png") or not fname.startswith(prefix):
                    continue
                stem = fname.rsplit(".", 1)[0]
                state = stem.split("--", 1)[1]
                pixmap = QPixmap(os.path.join(img_dir, fname))
                if pixmap.isNull():
                    continue
                images[state] = pixmap
            self._all_images[identity] = images

        if not self._all_images.get("maid") and not self._all_images.get("catgirl"):
            raise RuntimeError("未找到任何有效的 PNG 精灵图。")

        self.images = self._all_images.get(self._identity, self._all_images["maid"])

    def _init_state(self):
        """初始状态为 stand，窗口大小按 stand 图片调整。"""
        self.state = "stand"
        self.pre_state = "stand"
        if "stand" in self.images:
            self.setFixedSize(self.images["stand"].size())

    def _setup_timers(self):
        """动画、不活跃检测、触发状态超时 三个定时器。"""
        self._anim_frame = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(16)

        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._idle_timer.start(600_000)

        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.timeout.connect(self._on_state_timeout)

        self._game_timer = QTimer(self)
        self._game_timer.setSingleShot(True)
        self._game_timer.timeout.connect(self._on_game_timeout)

    def _setup_ui(self):
        """右键菜单策略。"""
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    # ============================== 状态机 ==============================

    def _change_state(self, new_state):
        """切换到新状态并调整窗口大小。"""
        if new_state not in self.images:
            return
        self.pre_state = self.state
        self.state = new_state
        self.setFixedSize(self.images[new_state].size())
        self.update()

    def _trigger_interaction(self):
        """根据当前状态和随机概率决定目标触发状态。"""
        r = random.random()
        if self.state == "stand":
            new_state = "cute" if r < 0.7 else "scaried"
        else:
            if r < 0.05:
                new_state = "cute"
            elif r < 0.25:
                new_state = "scaried"
            else:
                new_state = "apologize"

        self._change_state(new_state)
        self._state_timer.start(1_500)

    def _on_state_timeout(self):
        """触发状态超时回到 stand。"""
        if self._in_game:
            return
        if self._dance_active:
            self._on_dance_step()
            return
        if self.state in self._TRIGGER_STATES:
            self._change_state("stand")
            self._idle_timer.start(600_000)

    def _on_idle_timeout(self):
        """10 分钟无操作 → 进入 lazy。"""
        if self.state == "stand":
            self._change_state("lazy")

    # ============================== 工具方法 ==============================

    def _pet_side_pos(self, dialog):
        """计算宠物窗口旁边的对话框位置（优先右侧，超出屏幕则左侧）。"""
        pet_geo = self.frameGeometry()
        screen = QApplication.primaryScreen().size()
        x = pet_geo.right() + 10
        y = pet_geo.top()
        if x + dialog.width() > screen.width():
            x = pet_geo.left() - dialog.width() - 10
        if y + dialog.height() > screen.height():
            y = screen.height() - dialog.height()
        return max(0, x), max(0, y)

    # ============================== 浮动动画 ==============================

    def _float_offset(self):
        """各状态不同的 Y 轴浮动。"""
        t = self._anim_frame

        if self.state == "lazy":
            return math.sin(t * 0.02) * 2
        if self.state == "scaried":
            return math.sin(t * 0.30) * 4
        if self.state == "cute":
            return abs(math.sin(t * 0.08)) * 5
        if self.state == "apologize":
            return math.sin(t * 0.04) * 3

        return 0

    # ============================== 事件处理 ==============================

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()
            self._dragging = False
            event.accept()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._press_pos:
            dist = (event.globalPosition().toPoint() - self._press_pos).manhattanLength()
            if dist > 5:
                self._dragging = True
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._dragging:
                self._handle_click()
            self._dragging = False
            self._press_pos = None
            event.accept()

    def _handle_click(self):
        """左键点击：重置不活跃定时器，触发状态交互。"""
        self._idle_timer.start(600_000)
        if self.state in ("stand", "lazy"):
            self._trigger_interaction()

    def contextMenuEvent(self, event):
        """右键菜单：循环显示，子页面返回后回到主菜单。"""
        while True:
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background: #FFF8F0;
                    border: 1px solid #DAA520;
                    border-radius: 8px;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 6px 24px;
                    border-radius: 4px;
                    font-size: 14px;
                    color: #5D4037;
                }
                QMenu::item:selected {
                    background: #FFE4B5;
                }
            """)
            act_game = menu.addAction("游戏")
            act_dance = menu.addAction("跳舞")
            act_chat = menu.addAction("聊天")
            act_dress = menu.addAction("换装")
            act_exit = menu.addAction("退出")

            if self._in_game or self._dance_active or self._chat_dialog is not None:
                act_game.setEnabled(False)
                act_dance.setEnabled(False)
                act_chat.setEnabled(False)

            action = menu.exec(event.globalPos())
            menu.deleteLater()
            if action == act_exit:
                QApplication.quit()
                break
            elif action == act_game:
                self._start_game()
            elif action == act_dance:
                self._start_dance()
            elif action == act_chat:
                self._start_work()
            elif action == act_dress:
                self._switch_identity()
            else:
                break  # 点击菜单外退出

            # 聊天对话框已打开时不循环（modeless 对话框）
            if self._chat_dialog is not None:
                break

    # ============================== 换装 ==============================

    def _switch_identity(self):
        """切换女仆/猫娘身份，仅做指针交换并保存配置。"""
        self._identity = "catgirl" if self._identity == "maid" else "maid"
        try:
            with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            config["identity"] = self._identity
            with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except OSError:
            pass
        self.images = self._all_images[self._identity]
        self._init_state()
        self.update()

    # ============================== 绘制 ==============================

    def _tick(self):
        self._anim_frame += 1
        try:
            reply = self._reply_queue.get_nowait()
            self._on_api_reply(reply)
        except queue.Empty:
            pass
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        pixmap = self.images.get(self.state)
        if pixmap is not None:
            dy = self._float_offset()
        else:
            dy = 0

        painter.drawPixmap(
            QRect(0, int(dy), pixmap.width(), pixmap.height()),
            pixmap,
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())
