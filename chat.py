import os
import json
import queue
import threading
import urllib.request
import urllib.error
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                QPushButton, QLabel, QLineEdit,
                                QTextEdit, QFileDialog, QMessageBox)
from work import generate_document
from PySide6.QtGui import QGuiApplication


SYSTEM_PROMPT = """角色定义
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


class ChatMixin:
    """AI 聊天与配置管理混入类。"""

    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

    # ============================== 配置管理 ==============================

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
                color: black;
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

        title_text = "修改配置" if edit_mode else "请主人为女仆酱注入灵魂"
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
        btn_work = QPushButton("工作模式")
        btn_work.clicked.connect(self._work_mode)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self._close_chat)
        input_layout.addWidget(self._chat_input)
        input_layout.addWidget(btn_send)
        input_layout.addWidget(btn_work)
        input_layout.addWidget(btn_close)
        layout.addLayout(input_layout)

        self._chat_dialog = dialog
        self._chat_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

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
            with urllib.request.urlopen(req, timeout=180) as resp:
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

    # ============================== 工作模式 ==============================

    def _extract_json(self, text):
        """从 AI 回复中提取 JSON 代码块或花括号包裹的内容。"""
        import re
        # 尝试匹配 ```json ... ``` 代码块
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        # 尝试匹配最外层的 { ... }
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return None

    def _work_mode(self):
        """从最新 AI 回复中提取 JSON 并生成文档。"""
        # 找最后一条 assistant 消息
        last_reply = None
        for msg in reversed(self._chat_messages):
            if msg["role"] == "assistant":
                last_reply = msg["content"]
                break

        if not last_reply:
            QMessageBox.information(self, "提示", "还没有收到女仆酱的回复呢")
            return

        data = self._extract_json(last_reply)
        if not data:
            QMessageBox.warning(self, "提示", "女仆酱的最新回复中没有找到可用的文档数据。\n请让女仆酱先生成文档内容再试试。")
            return

        # 文件保存对话框，默认位置为桌面
        desktop = os.path.expanduser("~")
        default_name = data.get("title", "文档")
        ext_map = {"pptx": ".pptx", "docx": ".docx", "xlsx": ".xlsx", "pdf": ".pdf"}
        doc_type = data.get("type", "pptx")
        ext = ext_map.get(doc_type, ".pptx")
        default_path = os.path.join(desktop, default_name + ext)

        path, _ = QFileDialog.getSaveFileName(
            self._chat_dialog, "保存文档", default_path,
            f"文档 (*{ext});;所有文件 (*)",
        )
        if not path:
            return

        try:
            result = generate_document(data, path)
            QMessageBox.information(self, "成功", f"文档已生成：\n{result}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"文档生成失败：\n{str(e)}")
