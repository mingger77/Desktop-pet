import os
import json
import queue
import threading
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                QPushButton, QLabel, QLineEdit,
                                QTextEdit, QFileDialog, QMessageBox)
from PySide6.QtGui import QGuiApplication
from openai import OpenAI
from memory import MemoryStore


MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "memory",
        "description": "保存或删除长期记忆。记忆是跨会话持久化的，用于记住主人的偏好、习惯、个人信息等。女仆酱可以根据记忆更好地为主人服务。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove"],
                    "description": "add=保存新记忆, remove=删除已有记忆"
                },
                "content": {
                    "type": "string",
                    "description": "记忆内容，用简洁的陈述句描述"
                }
            },
            "required": ["action", "content"]
        }
    }
}


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
不提供医疗、法律、投资等专业建议
绝不主动询问或存储用户的敏感个人信息

	记忆系统
	女仆酱拥有跨会话的长期记忆能力。当主人说出以下内容时，必须立即使用 memory(action="add") 工具保存：
	- 个人偏好："我喜欢/不喜欢..."
	- 个人信息："我叫..."
	- 习惯日常："我经常..."
	- 重要事实："我住在..."
	使用简洁的陈述句保存，例如：memory(action="add", content="主人喜欢简洁的回答")
	memory 工具保存的内容会在未来所有对话中自动注入到系统提示词中

请以"女仆酱已就位，随时为您服务 (｡♥‿♥｡)"作为开场白。"""

_THEMES = {
    "maid": {
        "bg": "#FFF0F5", "border": "#FF69B4", "text_bold": "#FF1493",
        "label": "#8B4513", "input_border": "#FFB6C1", "btn_text": "#FF69B4",
    },
    "catgirl": {
        "bg": "#F0F0F0", "border": "#999999", "text_bold": "#333333",
        "label": "#8B4513", "input_border": "#CCCCCC", "btn_text": "#666666",
    },
}

_TUTORIAL_PAGES = [
    "1. 主人需要先访问 DeepSeek 开发者平台，网址是：https://platform.deepseek.com，要将网址复制然后粘贴到浏览器呦",
    "2. 点击页面右上角的“Sign In”或者“登录”按钮，选择“注册新账号”，用主人的邮箱和密码完成注册就好呢。注册完成后记得去邮箱里点击验证链接，这样账号才算真正激活哦（不然女仆酱也没法帮主人继续下一步呢）～",
    "3. 一定要完成实名认证， 这一步很重要很重要，如果没有完成实名认证是无法创建 API Key 的，系统只对认证通过的账户开放密钥创建权限呢",
    "4. 登录后，点击右上角头像 → \"账号设置\" → \"实名认证\"",
    "5. 选择 \"个人认证\" （如果主人是以企业身份注册，就选\"企业认证\"～）",
    "6. 按照提示上传 身份证正反面照片，填写真实姓名和身份证号，然后完成人脸识别或短信验证",
    "7. 提交后大约需要 1–3个工作日 审核，认证通过后页面会显示绿色的\"已通过\"标识",
    "8. 等认证通过，主人就可以继续下一步啦！",
    "9. 认证通过后，主人的 API Key 就可以生成啦～这个密钥就像是打开 API 服务的\"门禁卡\"，一定要小心保管哦！",
    "10. 进入左侧导航栏，点击 \"API管理\"→\"API Keys\"",
    "11. 点击 \"Create new secret key\" 按钮",
    "12. 在弹窗中为密钥起一个名字，小暖建议用\"项目名_环境\"的格式，比如\"myapp_production\"～这样以后管理起来特别清晰呢",
    "13. 点击确定后，系统会生成以 sk- 开头的密钥字符串",
    "14. 女仆酱的小tip:这个密钥只在生成时显示一次，关闭窗口后就再也看不到啦！主人在页面跳转前一定要立刻复制并保存在安全的地方，比如加密文件或密码管理器里。如果不小心弄丢了也没关系，重新创建一个新的就好，旧密钥失效即可～",
    "15. DeepSeek 采用预付费模式——就像给手机卡充话费一样，需要先充值才能调用 API 呢(｡•ᴗ•｡)。没有余额的话请求会返回 402 错误哦～",
    "16. 登录开发者平台，点击右上角头像 → \"账户余额\"或直接点左侧\"充值中心\"",
    "17. 点击\"立即充值\"，选择金额档位——最低单笔 ¥10 元，大约对应 10 万 Token 的调用额度",
    "18. 支付方式支持 微信支付、支付宝和银行转账～微信和支付宝是即时到账的，银行转账可能会慢一些",
    "19. 确认订单后点击\"去支付\"，扫码完成就行啦～",
    "20. 女仆酱的小tip：支付成功后系统通常会在 1–3 分钟 内更新余额，主人在\"用量中心\"页面可以看到实时余额和使用情况哦～小暖还建议主人在控制台 开启余额预警 功能，这样就不会因为突然没钱而中断调用啦",
    "21. 女仆酱的小tip：目前 DeepSeek 的价格相当实惠呢！以 deepseek-v4-flash 模型为例：\n    输入（缓存未命中）：1 元 / 百万 Token\n    输出：2 元 / 百万 Token\n    输入（缓存命中）：仅 0.02 元 / 百万 Token（超便宜！）\n    主人日常使用记账、笔记之类的小对话，消耗的 Token 其实非常非常少呢～充值 10 元可以用很久很久哦！",
    "22. 充值完成后，建议主人在 \"开始聊天\" 界面处向我说：\"女仆酱\"，如果我回复了，就说明一切正常～",
    "23. 如果返回正常的话，就说明完全 OK 啦！(≧▽≦)",
    "24. 主人如果后续需要详细阅读 API 文档，可以参考官方地址：https://api-docs.deepseek.com/zh-cn/，里面有完整的技术说明和代码示例呢～",
]


class ChatMixin:
    """AI 聊天与配置管理混入类。"""

    _CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

    # ============================== 配置管理 ==============================

    def _load_config(self):
        """加载 API 配置，文件不存在时创建默认配置。"""
        self._api_key = ""
        self._base_url = "https://api.deepseek.com"
        self._model = "deepseek-v4-flash"
        self._identity = "maid"
        if os.path.exists(self._CONFIG_FILE):
            try:
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._api_key = data.get("api_key", "")
                self._base_url = data.get("base_url", self._base_url)
                self._model = data.get("model", self._model)
                self._identity = data.get("identity", "maid")
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
                    "identity": self._identity,
                }, f, indent=2)
        except OSError:
            pass

    def _theme(self):
        """返回当前身份对应的主题色字典。"""
        return _THEMES.get(self._identity, _THEMES["maid"])

    # ============================== 工作 / AI 聊天 ==============================

    def _start_work(self):
        """进入工作模式：弹出工作模式选择菜单。"""
        self._idle_timer.stop()
        self._state_timer.stop()
        self._change_state("work")
        self._show_work_menu()

    def _show_work_menu(self):
        """已有 API key 时显示工作模式选择菜单。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("女仆酱")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        t = self._theme()
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {t["bg"]};
                border: 2px solid {t["border"]};
                border-radius: 12px;
                padding: 10px;
            }}
            QPushButton {{
                padding: 10px 30px;
                border: 1px solid {t["border"]};
                border-radius: 8px;
                background: white;
                color: {t["btn_text"]};
                font-size: 14px;
                min-width: 140px;
            }}
            QPushButton:hover {{
                background: #FFE4EC;
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(25, 25, 25, 25)

        label = QLabel("主人，有什么需要帮忙的吗")
        label.setStyleSheet(f"font-size: 15px; color: {t['text_bold']}; font-weight: bold;")
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
            if not self._api_key:
                QTimer.singleShot(200, lambda: self._show_setup_dialog(edit_mode=False))
            else:
                QTimer.singleShot(200, self._show_chat_dialog)
        elif choice == "config":
            QTimer.singleShot(200, lambda: self._show_setup_dialog(edit_mode=True))

    def _show_setup_dialog(self, edit_mode=False):
        """显示 API Key 设置对话框（支持编辑模式）。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("注入灵魂")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        t = self._theme()
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {t["bg"]};
                border: 2px solid {t["border"]};
                border-radius: 12px;
            }}
            QLabel {{
                color: {t["label"]};
                font-size: 13px;
            }}
            QLineEdit {{
                padding: 6px;
                border: 1px solid {t["input_border"]};
                border-radius: 4px;
                background: white;
                color: black;
                font-size: 13px;
            }}
            QPushButton {{
                padding: 8px 24px;
                border: 1px solid {t["border"]};
                border-radius: 6px;
                background: white;
                color: {t["btn_text"]};
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #FFE4EC;
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title_text = "修改配置" if edit_mode else "请主人为女仆酱注入灵魂"
        label = QLabel(title_text)
        label.setStyleSheet(f"font-size: 16px; color: {t["text_bold"]}; font-weight: bold;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        hint = QLabel("请输入 OpenAI 兼容 API 的信息：")
        layout.addWidget(hint)

        layout.addWidget(QLabel("API Key："))
        key_layout = QHBoxLayout()
        input_key = QLineEdit()
        key_visible = [False]
        if edit_mode and self._api_key:
            masked = self._api_key[:6] + "******"
            input_key.setText(masked)
            input_key.setPlaceholderText(masked)
            input_key.setEchoMode(QLineEdit.EchoMode.Password)
        else:
            input_key.setEchoMode(QLineEdit.EchoMode.Password)
            input_key.setPlaceholderText("sk-...")
        key_layout.addWidget(input_key)
        btn_toggle = QPushButton("显示")
        btn_toggle.setFixedWidth(50)
        btn_toggle.setStyleSheet("""
            QPushButton {
                padding: 4px 8px; border: 1px solid {t["input_border"]};
                border-radius: 4px; background: white;
                color: #FF69B4; font-size: 12px;
            }
            QPushButton:hover { background: #FFE4EC; }
        """)
        def toggle_key():
            key_visible[0] = not key_visible[0]
            if key_visible[0]:
                if edit_mode:
                    input_key.setText(self._api_key)
                input_key.setEchoMode(QLineEdit.EchoMode.Normal)
                btn_toggle.setText("隐藏")
            else:
                if edit_mode and self._api_key:
                    input_key.setText(self._api_key[:6] + "******")
                input_key.setEchoMode(QLineEdit.EchoMode.Password)
                btn_toggle.setText("显示")
        btn_toggle.clicked.connect(toggle_key)
        key_layout.addWidget(btn_toggle)
        layout.addLayout(key_layout)

        layout.addWidget(QLabel("Base URL："))
        input_url = QLineEdit()
        input_url.setText(self._base_url)
        input_url.setPlaceholderText("https://api.deepseek.com")
        layout.addWidget(input_url)

        layout.addWidget(QLabel("Model："))
        input_model = QLineEdit()
        input_model.setText(self._model)
        input_model.setPlaceholderText("deepseek-v4-flash")
        layout.addWidget(input_model)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("保存")
        btn_cancel = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        link = QPushButton("不懂点击这里")
        link.setStyleSheet("QPushButton { color: #4169E1; font-size: 11px; border: none; background: transparent; text-decoration: underline; } QPushButton:hover { color: #6495ED; }")
        link.clicked.connect(lambda: self._show_tutorial(dialog))
        layout.addWidget(link, alignment=Qt.AlignmentFlag.AlignCenter)

        btn_save.clicked.connect(lambda: self._on_config_saved(
            input_key.text().strip(), input_url.text().strip(),
            input_model.text().strip(), dialog, edit_mode))
        btn_cancel.clicked.connect(dialog.reject)
        dialog.rejected.connect(
            lambda: self._on_setup_cancelled(edit_mode))

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

    def _on_setup_cancelled(self, edit_mode):
        """配置对话框取消：回到工作菜单。"""
        self._change_state("work")
        QTimer.singleShot(200, self._show_work_menu)

    def _show_chat_dialog(self):
        """显示 AI 聊天对话框。"""
        if self._chat_dialog is not None:
            return
        if not hasattr(self, "_memory_store"):
            self._memory_store = MemoryStore()
        self._change_state("work")

        dialog = QDialog(self)
        dialog.setWindowTitle("女仆酱")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        t = self._theme()
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {t["bg"]};
                border: 2px solid {t["border"]};
                border-radius: 12px;
            }}
            QTextEdit {{
                border: 1px solid {t["input_border"]};
                border-radius: 6px;
                background: white;
                color: black;
                font-size: 13px;
                padding: 6px;
            }}
            QLineEdit {{
                border: 1px solid {t["input_border"]};
                border-radius: 4px;
                background: white;
                color: black;
                padding: 6px;
                font-size: 13px;
            }}
            QPushButton {{
                padding: 8px 16px;
                border: 1px solid {t["border"]};
                border-radius: 6px;
                background: white;
                color: {t["btn_text"]};
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #FFE4EC;
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("女仆酱 (｡♥‿♥｡)")
        title.setStyleSheet(f"font-size: 15px; color: {t["text_bold"]}; font-weight: bold;")
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
        input_layout.addWidget(self._chat_input)
        input_layout.addWidget(btn_send)
        layout.addLayout(input_layout)

        # 底部按钮行：关闭
        btn_layout = QHBoxLayout()
        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("""
            QPushButton {
                padding: 6px 10px; border: 1px solid #ccc;
                border-radius: 6px; background: white;
                color: #999; font-size: 12px;
            }
            QPushButton:hover { background: #F5F5F5; }
        """)
        btn_close.clicked.connect(self._close_chat)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

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

        self._auto_save_memory(msg)

        self._chat_input.clear()
        self._chat_display.append(f"主人：{msg}")
        self._chat_display.append("")
        self._chat_messages.append({"role": "user", "content": msg})
        self._chat_display.append("女仆酱：思考中...")
        threading.Thread(target=self._do_api_request, daemon=True).start()

    # ============================== 主动记忆检测 ==============================

    def _auto_save_memory(self, text):
        """检测用户消息中的记忆线索，自动保存到长期记忆。
        作为工具调用的补充：模型可能不会每次都自主调用 memory 工具，
        客户端主动检测常见记忆模式来兜底。"""
        memory_keywords = [
            "记住", "记得", "我叫", "我是", "我的名字",
            "我喜欢", "我不喜欢", "我愛", "我討厭",
            "住在", "我的生日", "我住在",
        ]
        for kw in memory_keywords:
            if kw in text:
                self._memory_store.add(text.strip())
                return True
        return False

    def _do_api_request(self):
        """使用 OpenAI SDK 调用 API（非流式），支持记忆工具。"""
        try:
            client = OpenAI(api_key=self._api_key, base_url=self._base_url)

            # 注入长期记忆
            memory_block = self._memory_store.format_for_prompt()
            messages = list(self._chat_messages)
            if memory_block:
                messages.insert(1, {
                    "role": "system",
                    "content": memory_block,
                })

            kwargs = {
                "model": self._model,
                "messages": messages,
                "tools": [MEMORY_TOOL],
            }

            resp = client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message

            # 处理记忆工具调用
            if msg.tool_calls:
                self._chat_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in msg.tool_calls
                    ],
                })
                for tc in msg.tool_calls:
                    self._chat_messages.append(self._handle_memory_tool(tc))

                resp2 = client.chat.completions.create(
                    model=self._model,
                    messages=self._chat_messages,
                    tools=[MEMORY_TOOL],
                )
                reply = resp2.choices[0].message.content or ""
                self._chat_messages.append({"role": "assistant", "content": reply})
                self._reply_queue.put(reply)
            else:
                reply = msg.content or ""
                self._chat_messages.append({"role": "assistant", "content": reply})
                self._reply_queue.put(reply)

        except Exception as e:
            self._reply_queue.put(f"啊哦，出错了呢 (｡•́︿•̀｡) {str(e)}")

    def _handle_memory_tool(self, tool_call):
        """执行记忆工具调用，返回 tool 结果消息。"""
        import json
        try:
            args = json.loads(tool_call.function.arguments)
            action = args.get("action", "")
            content = args.get("content", "")
            if action == "add":
                ok = self._memory_store.add(content)
                usage = self._memory_store.usage_percent()
                msg = f"记忆已保存 (使用率 {usage}%)" if ok else "记忆保存失败（可能已存在或超限）"
            elif action == "remove":
                ok = self._memory_store.remove(content)
                msg = "记忆已删除" if ok else "未找到该记忆"
            else:
                msg = f"未知操作: {action}"
            return {"role": "tool", "tool_call_id": tool_call.id, "content": msg}
        except Exception as e:
            return {"role": "tool", "tool_call_id": tool_call.id, "content": f"执行失败: {str(e)}"}

    def _on_api_reply(self, text):
        """在 UI 中显示完整 API 回复。"""
        self._chat_display.append(f"女仆酱：{text}")
        self._chat_display.append("")

    def _close_chat(self):
        """关闭聊天窗口，回到工作菜单。"""
        self._chat_dialog.close()
        self._chat_dialog = None
        self._change_state("work")
        self._show_work_menu()

    # ============================== 高级设置 ==============================

    def _show_advanced_settings(self):
        """弹出高级设置对话框（联网模式 / 工作模式 / 返回）。"""
        dialog = QDialog(self._chat_dialog)
        dialog.setWindowTitle("高级设置")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        t = self._theme()
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {t["bg"]};
                border: 2px solid {t["border"]};
                border-radius: 12px;
                padding: 10px;
            }}
            QPushButton {{
                padding: 10px 30px;
                border: 1px solid #ccc;
                border-radius: 8px;
                background: white;
                color: black;
                font-size: 14px;
                min-width: 160px;
            }}
            QPushButton:hover {{
                background: #F5F5F5;
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        label = QLabel("高级设置")
        label.setStyleSheet(f"font-size: 15px; color: {t['text_bold']}; font-weight: bold;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        # 联网模式按钮
        btn_web = QPushButton("联网模式")
        if self._web_search_enabled:
            btn_web.setStyleSheet("""
                QPushButton {
                    padding: 10px 30px; border: 1px solid #FF69B4;
                    border-radius: 8px; background: {t["input_border"]};
                    color: black; font-size: 14px; min-width: 160px;
                }
            """)
        layout.addWidget(btn_web)

        def toggle_web():
            self._web_search_enabled = not self._web_search_enabled
            if self._web_search_enabled:
                btn_web.setStyleSheet("""
                    QPushButton {
                        padding: 10px 30px; border: 1px solid #FF69B4;
                        border-radius: 8px; background: {t["input_border"]};
                        color: black; font-size: 14px; min-width: 160px;
                    }
                """)
            else:
                btn_web.setStyleSheet("""
                    QPushButton {
                        padding: 10px 30px; border: 1px solid #ccc;
                        border-radius: 8px; background: white;
                        color: black; font-size: 14px; min-width: 160px;
                    }
                """)
        btn_web.clicked.connect(toggle_web)

        # 工作模式按钮
        btn_work_mode = QPushButton("工作模式")
        if self._work_mode_enabled:
            btn_work_mode.setStyleSheet("""
                QPushButton {
                    padding: 10px 30px; border: 1px solid #FF69B4;
                    border-radius: 8px; background: {t["input_border"]};
                    color: black; font-size: 14px; min-width: 160px;
                }
            """)
        layout.addWidget(btn_work_mode)

        def toggle_work_mode():
            self._work_mode_enabled = not self._work_mode_enabled
            if self._work_mode_enabled:
                btn_work_mode.setStyleSheet("""
                    QPushButton {
                        padding: 10px 30px; border: 1px solid #FF69B4;
                        border-radius: 8px; background: {t["input_border"]};
                        color: black; font-size: 14px; min-width: 160px;
                    }
                """)
            else:
                btn_work_mode.setStyleSheet("""
                    QPushButton {
                        padding: 10px 30px; border: 1px solid #ccc;
                        border-radius: 8px; background: white;
                        color: black; font-size: 14px; min-width: 160px;
                    }
                """)
        btn_work_mode.clicked.connect(toggle_work_mode)

        # 返回按钮
        btn_back = QPushButton("返回")
        btn_back.setStyleSheet("""
            QPushButton {
                padding: 8px 20px; border: 1px solid #ccc;
                border-radius: 6px; background: white;
                color: #999; font-size: 13px; min-width: 100px;
            }
            QPushButton:hover { background: #F5F5F5; }
        """)
        btn_back.clicked.connect(dialog.accept)
        layout.addWidget(btn_back, alignment=Qt.AlignmentFlag.AlignCenter)

        dialog.setFixedSize(220, 260)
        pet_geo = self._chat_dialog.frameGeometry() if self._chat_dialog else self.frameGeometry()
        screen = QGuiApplication.primaryScreen().size()
        x = pet_geo.right() + 10
        y = pet_geo.top()
        if y + dialog.height() > screen.height():
            y = screen.height() - dialog.height()
        dialog.move(max(0, x), max(0, y))
        dialog.exec()

    # ============================== 教程 ==============================

    def _show_tutorial(self, parent_dialog=None):
        """显示 24 页教程对话框。"""
        dialog = QDialog(parent_dialog or self)
        dialog.setWindowTitle("教程")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        t = self._theme()
        dialog.setStyleSheet(f"""
            QDialog {{
                background: {t["bg"]};
                border: 2px solid {t["border"]};
                border-radius: 12px;
            }}
            QTextEdit {{
                border: 1px solid {t["input_border"]};
                border-radius: 6px;
                background: white;
                color: black;
                font-size: 13px;
                padding: 8px;
            }}
            QPushButton {{
                padding: 8px 20px;
                border: 1px solid {t["border"]};
                border-radius: 6px;
                background: white;
                color: {t["btn_text"]};
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: #FFE4EC;
            }}
            QPushButton:disabled {{
                border-color: #ccc;
                color: #ccc;
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("教程")
        title.setStyleSheet(f"font-size: 16px; color: {t['text_bold']}; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setMaximumHeight(300)
        layout.addWidget(text_edit)

        nav_layout = QHBoxLayout()
        btn_prev = QPushButton("上一页")
        btn_next = QPushButton("下一页")
        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("""
            QPushButton {
                padding: 8px 16px; border: 1px solid #ccc;
                border-radius: 6px; background: white;
                color: #999; font-size: 12px;
            }
            QPushButton:hover { background: #F5F5F5; }
        """)
        btn_close.clicked.connect(dialog.reject)
        page_label = QLabel("第 1 / 24 页")
        page_label.setStyleSheet("color: #8B4513; font-size: 13px;")
        nav_layout.addWidget(btn_prev)
        nav_layout.addStretch()
        nav_layout.addWidget(page_label)
        nav_layout.addStretch()
        nav_layout.addWidget(btn_close)
        nav_layout.addWidget(btn_next)
        layout.addLayout(nav_layout)

        current_page = [0]

        def show_page():
            text_edit.setPlainText(_TUTORIAL_PAGES[current_page[0]])
            page_label.setText(f"第 {current_page[0] + 1} / {len(_TUTORIAL_PAGES)} 页")
            btn_prev.setEnabled(current_page[0] > 0)
            is_last = current_page[0] == len(_TUTORIAL_PAGES) - 1
            btn_next.setText("完成" if is_last else "下一页")

        btn_prev.clicked.connect(
            lambda: (list.__setitem__(current_page, 0, current_page[0] - 1), show_page()))
        btn_next.clicked.connect(
            lambda: dialog.accept() if current_page[0] == len(_TUTORIAL_PAGES) - 1
            else (list.__setitem__(current_page, 0, current_page[0] + 1), show_page()))

        show_page()
        dialog.setFixedSize(400, 400)
        screen = QGuiApplication.primaryScreen().size()
        dialog.move((screen.width() - dialog.width()) // 2,
                     (screen.height() - dialog.height()) // 2)
        dialog.exec()

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
