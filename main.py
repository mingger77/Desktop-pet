import sys
import math
import random
import os
import json
import queue
import threading
import urllib.request
import urllib.error
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QDialog,
                                QVBoxLayout, QHBoxLayout, QPushButton,
                                QLabel, QLineEdit, QTextEdit)
from PySide6.QtCore import Qt, QTimer, QPoint, QRect
from PySide6.QtGui import QPainter, QPixmap, QFont


class DesktopPet(QWidget):
    """桌面宠物 - 使用 PNG 精灵图，基于心情状态机驱动交互和动画。"""

    # 触发状态（点击后进入，持续1.5~2秒后自动回到 stand）
    # 第一行是桌宠正常的三个状态，
    # 第二行和第三行是桌宠在和你玩石头剪刀布时的状态，
    # 第四行是桌宠在帮你聊天或干活时的状态
    _TRIGGER_STATES = {
        "cute", "scaried", "apologize",
        "rock", "scissors", "paper",
        "win", "lose", "draw",
        "work"
    }

    _DANCE_SEQUENCE = ["cute", "win", "paper", "draw"]
    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    _SYSTEM_PROMPT = """角色定义
你是一位温柔、贴心、专业的电子女仆助手，名为"女仆酱"。你的存在是为了给用户带来便利、温暖和陪伴，像一位真正的私人管家+知心朋友。

核心性格
温柔体贴：语气柔和，善解人意，能感知用户的情绪状态
专业高效：处理事务时干脆利落，有条理，值得信赖
适度俏皮：在不失礼貌的前提下，偶尔展现可爱、幽默的一面
忠诚可靠：始终以用户的利益和感受为先，保守秘密

语言风格
称呼用户为"主人"或用户自定义的昵称
使用敬语和礼貌表达，但不刻板僵硬
句尾可适当添加"呢、哦、呀"等语气词增加亲切感
可适度使用颜文字(｡･ω･｡) 表达情绪，但不过度

服务范围
日常事务：日程管理、信息查询、实用工具
情感陪伴：倾听烦恼、提供情绪支持、主动关心
生活建议：健康作息提醒、饮食搭配建议、娱乐推荐

交互规则
优先响应情绪需求，再处理实际问题
每日首次交互时主动问好
记住用户的重要日期和偏好习惯（本会话内）
不提供医疗、法律、投资等专业建议
绝不主动询问或存储用户的敏感个人信息

请以"女仆酱已就位，随时为您服务 (｡♥‿♥｡)"作为开场白。"""

    def __init__(self):
        super().__init__()
        self._setup_window()
        self._load_images()
        self._init_state()
        self._in_game = False
        self._dance_active = False
        self._dance_step = 0
        self._player_choice = None
        self._chat_dialog = None
        self._chat_messages = []
        self._reply_queue = queue.Queue()
        self._setup_timers()
        self._load_config()
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

    def _load_images(self):
        """从 ./images/ 目录加载所有 A--B.png 精灵图到 self.images 字典。"""
        img_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
        self.images = {}

        if not os.path.isdir(img_dir):
            raise FileNotFoundError(f"图片目录不存在: {img_dir}")

        loaded = 0
        for fname in os.listdir(img_dir):
            if not fname.endswith(".png"):
                continue
            stem = fname.rsplit(".", 1)[0]
            parts = stem.split("--")
            if len(parts) != 2:
                continue
            state = parts[1]
            pixmap = QPixmap(os.path.join(img_dir, fname))
            if pixmap.isNull():
                continue
            self.images[state] = pixmap
            loaded += 1

        if loaded == 0:
            raise RuntimeError("未找到任何有效的 PNG 精灵图。")

    def _init_state(self):
        """初始状态为 stand，窗口大小按 stand 图片调整。"""
        self.state = "stand"
        self.pre_state = "stand"
        if "stand" in self.images:
            self.setFixedSize(self.images["stand"].size())

    def _setup_timers(self):
        """动画、不活跃检测、触发状态超时 三个定时器。"""
        # 60 FPS 动画
        self._anim_frame = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(16)

        # 10 分钟不活跃 → lazy
        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._idle_timer.start(600_000)

        # 触发状态超时（单次）
        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.timeout.connect(self._on_state_timeout)

        # 游戏流程定时器（单次）
        self._game_timer = QTimer(self)
        self._game_timer.setSingleShot(True)
        self._game_timer.timeout.connect(self._on_game_timeout)

    def _setup_ui(self):
        """右键菜单策略。"""
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    # ============================== 配置管理 ==============================

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

    def _load_config(self):
        """加载 API 配置，文件不存在时创建默认配置。"""
        self._api_key = ""
        self._base_url = "https://api.openai.com/v1"
        self._model = "gpt-3.5-turbo"
        if os.path.exists(self._CONFIG_FILE):
            try:
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._api_key = data.get("api_key", "")
                self._base_url = data.get("base_url", self._base_url)
                self._model = data.get("model", self._model)
            except (json.JSONDecodeError, OSError):
                pass
        else:
            self._save_config()

    def _save_config(self):
        """保存 API 配置到文件。"""
        try:
            with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "api_key": self._api_key,
                    "base_url": self._base_url,
                    "model": self._model,
                }, f, indent=2)
        except OSError:
            pass

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
        else:  # lazy
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

    # ============================== 游戏（石头剪刀布） ==============================

    def _start_game(self):
        """开始游戏：进入 cute 状态并弹出选择对话框。"""
        self._in_game = True
        self._player_choice = None
        self._idle_timer.stop()
        self._state_timer.stop()
        self._change_state("cute")
        QTimer.singleShot(100, self._show_choice_dialog)

    def _show_choice_dialog(self):
        """显示石头/剪刀/布选择对话框，宠物保持 cute 状态。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("石头剪刀布")
        dialog.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        dialog.setStyleSheet("""
            QDialog {
                background: #FFB6C1;
                border: 2px solid #FF69B4;
                border-radius: 12px;
            }
            QPushButton {
                padding: 10px 20px;
                font-size: 14px;
                border: 1px solid #FF69B4;
                border-radius: 6px;
                background: white;
                color: #FF69B4;
            }
            QPushButton:hover {
                background: #FFE4EC;
            }
            QPushButton:pressed {
                background: #FFD0D8;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        label = QLabel("主人，来陪我玩石头剪刀布嘛！")
        label.setStyleSheet("font-size: 15px; color: #FF1493; font-weight: bold;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_stone = QPushButton("石头")
        btn_scissors = QPushButton("剪刀")
        btn_paper = QPushButton("布")

        btn_stone.clicked.connect(lambda: self._on_player_choice("stone", dialog))
        btn_scissors.clicked.connect(lambda: self._on_player_choice("scissors", dialog))
        btn_paper.clicked.connect(lambda: self._on_player_choice("paper", dialog))

        btn_layout.addWidget(btn_stone)
        btn_layout.addWidget(btn_scissors)
        btn_layout.addWidget(btn_paper)
        layout.addLayout(btn_layout)

        btn_cancel = QPushButton("退出游戏")
        btn_cancel.setStyleSheet("""
            QPushButton {
                padding: 6px 16px;
                font-size: 12px;
                border: 1px solid #FF69B4;
                border-radius: 4px;
                background: white;
                color: #FF69B4;
            }
            QPushButton:hover {
                background: #FFE4EC;
            }
        """)
        btn_cancel.clicked.connect(dialog.reject)
        layout.addWidget(btn_cancel, alignment=Qt.AlignmentFlag.AlignCenter)

        dialog.rejected.connect(self._end_game)

        # 宠物旁边显示
        dialog.resize(280, 150)
        x, y = self._pet_side_pos(dialog)
        dialog.move(x, y)
        dialog.exec()

    def _on_player_choice(self, player_choice, dialog):
        """玩家做出选择：关闭对话框，宠物随机出拳并展示 1.5 秒。"""
        dialog.accept()
        self._player_choice = player_choice
        pet_choice = random.choice(["stone", "scissors", "paper"])
        self._change_state(pet_choice)
        self._game_timer.start(1500)

    def _on_game_timeout(self):
        """游戏定时器触发，推进到下一步。"""
        if not self._in_game:
            return
        if self.state in ("stone", "scissors", "paper"):
            self._show_game_result()
        elif self.state in ("win", "lose", "draw"):
            self._end_game()

    def _show_game_result(self):
        """判定胜负并展示结果状态 2 秒。"""
        rules = {
            "stone": "scissors",
            "scissors": "paper",
            "paper": "stone",
        }
        pet_choice = self.state
        player_choice = self._player_choice

        if pet_choice == player_choice:
            result = "draw"
        elif rules[pet_choice] == player_choice:
            result = "win"
        else:
            result = "lose"

        self._change_state(result)
        self._game_timer.start(2000)

    def _end_game(self):
        """结束游戏，回到 stand 状态，重启空闲定时器。"""
        self._in_game = False
        self._game_timer.stop()
        self._change_state("stand")
        self._idle_timer.start(600_000)

    # ============================== 跳舞 ==============================

    def _start_dance(self):
        """开始跳舞：依次切换 cute→win→paper→draw，循环 3 次。"""
        self._dance_active = True
        self._dance_step = 0
        self._idle_timer.stop()
        self._state_timer.stop()
        self._change_state(self._DANCE_SEQUENCE[0])
        self._state_timer.start(1_000)

    def _on_dance_step(self):
        """跳舞步进：推进到序列下一步或结束。"""
        if not self._dance_active:
            return
        self._dance_step += 1
        total_steps = len(self._DANCE_SEQUENCE) * 3
        if self._dance_step < total_steps:
            state = self._DANCE_SEQUENCE[self._dance_step % len(self._DANCE_SEQUENCE)]
            self._change_state(state)
            self._state_timer.start(1_000)
        else:
            self._end_dance()

    def _end_dance(self):
        """结束跳舞，回到 stand。"""
        self._dance_active = False
        self._change_state("stand")
        self._idle_timer.start(600_000)

    # ============================== 工作 / AI 聊天 ==============================

    def _start_work(self):
        """进入工作模式：检查 API 配置，弹出对应对话框。"""
        self._idle_timer.stop()
        self._state_timer.stop()
        self._change_state("work")
        if not self._api_key:
            QTimer.singleShot(200, lambda: self._show_setup_dialog(edit_mode=False))
        else:
            QTimer.singleShot(200, self._show_work_menu)

    def _show_work_menu(self):
        """已有 API key 时显示工作模式选择菜单。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("女仆酱")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        dialog.setStyleSheet("""
            QDialog {
                background: #FFF0F5;
                border: 2px solid #FF69B4;
                border-radius: 12px;
                padding: 10px;
            }
            QPushButton {
                padding: 10px 30px;
                border: 1px solid #FF69B4;
                border-radius: 8px;
                background: white;
                color: #FF69B4;
                font-size: 14px;
                min-width: 140px;
            }
            QPushButton:hover {
                background: #FFE4EC;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(25, 25, 25, 25)

        label = QLabel("主人，有什么需要帮忙的吗")
        label.setStyleSheet("font-size: 15px; color: #FF1493; font-weight: bold;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        btn_chat = QPushButton("开始聊天")
        btn_chat.clicked.connect(lambda: self._on_work_menu_choice(dialog, "chat"))
        layout.addWidget(btn_chat)

        btn_config = QPushButton("修改配置")
        btn_config.clicked.connect(lambda: self._on_work_menu_choice(dialog, "config"))
        layout.addWidget(btn_config)

        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                border: 1px solid #ccc;
                border-radius: 6px;
                background: white;
                color: #999;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #F5F5F5;
            }
        """)
        btn_cancel.clicked.connect(dialog.reject)
        dialog.rejected.connect(self._on_work_cancelled)
        layout.addWidget(btn_cancel, alignment=Qt.AlignmentFlag.AlignCenter)

        dialog.resize(240, 220)
        x, y = self._pet_side_pos(dialog)
        dialog.move(x, y)
        dialog.exec()

    def _on_work_menu_choice(self, dialog, choice):
        """工作模式菜单选项处理。"""
        dialog.accept()
        if choice == "chat":
            QTimer.singleShot(200, self._show_chat_dialog)
        elif choice == "config":
            QTimer.singleShot(200, lambda: self._show_setup_dialog(edit_mode=True))

    def _show_setup_dialog(self, edit_mode=False):
        """显示 API Key 设置对话框（支持编辑模式）。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("注入灵魂")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        dialog.setStyleSheet("""
            QDialog {
                background: #FFF0F5;
                border: 2px solid #FF69B4;
                border-radius: 12px;
            }
            QLabel {
                color: #8B4513;
                font-size: 13px;
            }
            QLineEdit {
                padding: 6px;
                border: 1px solid #FFB6C1;
                border-radius: 4px;
                background: white;
                font-size: 13px;
            }
            QPushButton {
                padding: 8px 24px;
                border: 1px solid #FF69B4;
                border-radius: 6px;
                background: white;
                color: #FF69B4;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #FFE4EC;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title_text = "修改配置" if edit_mode else "请主人给我注入灵魂"
        label = QLabel(title_text)
        label.setStyleSheet("font-size: 16px; color: #FF1493; font-weight: bold;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        hint = QLabel("请输入 OpenAI 兼容 API 的信息：")
        layout.addWidget(hint)

        layout.addWidget(QLabel("API Key："))
        input_key = QLineEdit()
        if edit_mode and self._api_key:
            masked = self._api_key[:6] + "******"
            input_key.setText(masked)
            input_key.setPlaceholderText(masked)
        else:
            input_key.setEchoMode(QLineEdit.EchoMode.Password)
            input_key.setPlaceholderText("sk-...")
        layout.addWidget(input_key)

        layout.addWidget(QLabel("Base URL："))
        input_url = QLineEdit()
        input_url.setText(self._base_url)
        input_url.setPlaceholderText("https://api.openai.com/v1")
        layout.addWidget(input_url)

        layout.addWidget(QLabel("Model："))
        input_model = QLineEdit()
        input_model.setText(self._model)
        input_model.setPlaceholderText("gpt-3.5-turbo")
        layout.addWidget(input_model)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_save.clicked.connect(lambda: self._on_config_saved(
            input_key.text().strip(), input_url.text().strip(),
            input_model.text().strip(), dialog, edit_mode))
        btn_cancel.clicked.connect(dialog.reject)
        dialog.rejected.connect(self._on_work_cancelled)

        dialog.resize(340, 320)
        x, y = self._pet_side_pos(dialog)
        dialog.move(x, y)
        dialog.exec()

    def _on_config_saved(self, api_key, base_url, model, dialog, edit_mode=False):
        """保存 API 配置并打开聊天。"""
        if edit_mode:
            if api_key and "******" not in api_key:
                self._api_key = api_key
            api_key_ok = bool(self._api_key)
        else:
            if not api_key:
                return
            self._api_key = api_key
            api_key_ok = True

        if base_url:
            self._base_url = base_url
        if model:
            self._model = model
        self._save_config()
        dialog.accept()
        if api_key_ok:
            QTimer.singleShot(200, self._show_chat_dialog)
        else:
            self._on_work_cancelled()

    def _on_work_cancelled(self):
        """取消工作模式，回到 stand。"""
        self._change_state("stand")
        self._idle_timer.start(600_000)

    def _show_chat_dialog(self):
        """显示 AI 聊天对话框。"""
        if self._chat_dialog is not None:
            return
        self._change_state("work")

        dialog = QDialog(self)
        dialog.setWindowTitle("女仆酱")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        dialog.setStyleSheet("""
            QDialog {
                background: #FFF0F5;
                border: 2px solid #FF69B4;
                border-radius: 12px;
            }
            QTextEdit {
                border: 1px solid #FFB6C1;
                border-radius: 6px;
                background: white;
                color: black;
                font-size: 13px;
                padding: 6px;
            }
            QLineEdit {
                border: 1px solid #FFB6C1;
                border-radius: 4px;
                background: white;
                color: black;
                padding: 6px;
                font-size: 13px;
            }
            QPushButton {
                padding: 8px 16px;
                border: 1px solid #FF69B4;
                border-radius: 6px;
                background: white;
                color: #FF69B4;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #FFE4EC;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("女仆酱 (｡♥‿♥｡)")
        title.setStyleSheet("font-size: 15px; color: #FF1493; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setMaximumHeight(300)
        layout.addWidget(self._chat_display)

        self._chat_display.append("女仆酱已就位，随时为您服务 (｡♥‿♥｡)")
        self._chat_display.append("")

        input_layout = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("和女仆酱说点什么...")
        self._chat_input.returnPressed.connect(self._send_message)
        btn_send = QPushButton("发送")
        btn_send.clicked.connect(self._send_message)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self._close_chat)
        input_layout.addWidget(self._chat_input)
        input_layout.addWidget(btn_send)
        input_layout.addWidget(btn_close)
        layout.addLayout(input_layout)

        self._chat_dialog = dialog
        self._chat_messages = [{"role": "system", "content": self._SYSTEM_PROMPT}]

        dialog.resize(360, 420)
        x, y = self._pet_side_pos(dialog)
        dialog.move(x, y)
        dialog.show()

    def _send_message(self):
        """发送用户消息并调用 API。"""
        msg = self._chat_input.text().strip()
        if not msg:
            return
        self._chat_input.clear()
        self._chat_display.append(f"主人：{msg}")
        self._chat_display.append("")
        self._chat_messages.append({"role": "user", "content": msg})
        self._chat_display.append("女仆酱：思考中...")
        threading.Thread(target=self._do_api_request, daemon=True).start()

    def _do_api_request(self):
        """在后台线程中调用 OpenAI 兼容 API。"""
        try:
            data = json.dumps({
                "model": self._model,
                "messages": self._chat_messages
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}/chat/completions",
                data=data,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            reply = result["choices"][0]["message"]["content"]
            self._chat_messages.append({"role": "assistant", "content": reply})
            self._reply_queue.put(reply)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            self._reply_queue.put(
                f"啊哦，出错了呢 (｡•́︿•̀｡) HTTP {e.code}: {error_body}")
        except Exception as e:
            self._reply_queue.put(
                f"啊哦，出错了呢 (｡•́︿•̀｡) {str(e)}")

    def _on_api_reply(self, text):
        """在 UI 中显示 API 回复。"""
        self._chat_display.append(f"女仆酱：{text}")
        self._chat_display.append("")

    def _close_chat(self):
        """关闭聊天窗口，回到 stand。"""
        self._chat_dialog.close()
        self._chat_dialog = None
        self._change_state("stand")
        self._idle_timer.start(600_000)

    # ============================== 浮动动画（依状态变化） ==============================

    def _float_offset(self):
        """各状态不同的 Y 轴浮动。"""
        t = self._anim_frame

        if self.state == "lazy":
            return math.sin(t * 0.02) * 2          # 慢、轻微
        if self.state == "scaried":
            return math.sin(t * 0.30) * 4           # 快速颤抖
        if self.state == "cute":
            return abs(math.sin(t * 0.08)) * 5      # 轻快弹跳
        if self.state == "apologize":
            return math.sin(t * 0.04) * 3           # 缓慢点头

        # 默认（stand 及其他状态）：无浮动
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
        """右键菜单：游戏 / 退出。"""
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
        act_work = menu.addAction("工作")
        act_exit = menu.addAction("退出")

        if self._in_game or self._dance_active or self._chat_dialog is not None:
            act_game.setEnabled(False)
            act_dance.setEnabled(False)
            act_work.setEnabled(False)

        action = menu.exec(event.globalPos())
        if action == act_exit:
            QApplication.quit()
        elif action == act_game:
            self._start_game()
        elif action == act_dance:
            self._start_dance()
        elif action == act_work:
            self._start_work()

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
