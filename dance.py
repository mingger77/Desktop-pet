import os
import json
import random
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                QPushButton, QLabel, QCheckBox,
                                QSpinBox, QListWidget, QListWidgetItem,
                                QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


class DanceSelectorDialog(QDialog):
    """跳舞模式选择对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._choice = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("选择跳舞模式")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("""
            QDialog {
                background: #FFF0F5;
                border: 2px solid #FF69B4;
                border-radius: 12px;
                padding: 10px;
            }
            QPushButton {
                padding: 10px 20px;
                border: 1px solid #FF69B4;
                border-radius: 8px;
                background: white;
                color: #FF69B4;
                font-size: 13px;
                min-width: 200px;
            }
            QPushButton:hover {
                background: #FFE4EC;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        label = QLabel("请选择跳舞模式")
        label.setStyleSheet("font-size: 15px; color: #FF1493; font-weight: bold;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        btn_a = QPushButton("主人，让女仆酱为你随便跳一支舞吧")
        btn_a.clicked.connect(lambda: self._pick("random"))
        layout.addWidget(btn_a)

        btn_b = QPushButton("让女仆酱按照主人的指示跳舞吧")
        btn_b.clicked.connect(lambda: self._pick("saved"))
        layout.addWidget(btn_b)

        btn_c = QPushButton("让主人为女仆酱定制舞蹈吧")
        btn_c.clicked.connect(lambda: self._pick("custom"))
        layout.addWidget(btn_c)

        btn_back = QPushButton("返回")
        btn_back.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                border: 1px solid #ccc;
                border-radius: 6px;
                background: white;
                color: #999;
                font-size: 13px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: #F5F5F5;
            }
        """)
        btn_back.clicked.connect(self.reject)
        layout.addWidget(btn_back, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setFixedSize(300, 280)

    def _pick(self, choice):
        self._choice = choice
        self.accept()

    def _position_near_parent(self):
        parent = self.parent()
        if parent:
            pet_geo = parent.frameGeometry()
            screen = QGuiApplication.primaryScreen().size()
            x = pet_geo.right() + 10
            y = pet_geo.top()
            if x + self.width() > screen.width():
                x = pet_geo.left() - self.width() - 10
            if y + self.height() > screen.height():
                y = screen.height() - self.height()
            self.move(max(0, x), max(0, y))

    def get_choice(self):
        """返回 'random' / 'saved' / 'custom' / None。"""
        self._position_near_parent()
        self.exec()
        return self._choice


class DanceCustomizeDialog(QDialog):
    """自定义编舞对话框：选择 3~6 个动作、循环次数 2~4。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("自定义舞蹈")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("""
            QDialog {
                background: #FFF0F5;
                border: 2px solid #FF69B4;
                border-radius: 12px;
            }
            QLabel {
                color: #8B4513;
                font-size: 13px;
            }
            QCheckBox {
                color: #8B4513;
                font-size: 13px;
                spacing: 8px;
            }
            QSpinBox {
                padding: 4px;
                border: 1px solid #FFB6C1;
                border-radius: 4px;
                background: white;
                color: black;
                font-size: 13px;
            }
            QPushButton {
                padding: 8px 20px;
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

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("请为女仆酱选择舞蹈动作吧（3~6 个）")
        title.setStyleSheet("font-size: 15px; color: #FF1493; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._checkboxes = []
        for i in range(1, 7):
            cb = QCheckBox(f"动作 {i}")
            cb.setChecked(True if i <= 4 else False)
            self._checkboxes.append(cb)
            layout.addWidget(cb)

        loop_layout = QHBoxLayout()
        loop_layout.addWidget(QLabel("循环次数："))
        self._spin_loops = QSpinBox()
        self._spin_loops.setMinimum(2)
        self._spin_loops.setMaximum(4)
        self._spin_loops.setValue(3)
        loop_layout.addWidget(self._spin_loops)
        loop_layout.addStretch()
        layout.addLayout(loop_layout)

        btn_layout = QHBoxLayout()
        btn_play = QPushButton("播放")
        btn_play.clicked.connect(self._on_play)
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self._on_save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_play)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        self.setFixedSize(280, 380)

    def _get_selected_poses(self):
        selected = []
        for i, cb in enumerate(self._checkboxes):
            if cb.isChecked():
                selected.append(f"dance{i + 1}")
        return selected

    def _on_play(self):
        poses = self._get_selected_poses()
        if len(poses) < 3:
            QMessageBox.warning(self, "提示", "请至少选择 3 个动作")
            return
        loops = self._spin_loops.value()
        self._result = ("play", poses, loops)
        self.accept()

    def _on_save(self):
        poses = self._get_selected_poses()
        if len(poses) < 3:
            QMessageBox.warning(self, "提示", "请至少选择 3 个动作")
            return
        loops = self._spin_loops.value()
        self._result = ("save", poses, loops)
        self.accept()

    def _position_near_parent(self):
        parent = self.parent()
        if parent:
            pet_geo = parent.frameGeometry()
            screen = QGuiApplication.primaryScreen().size()
            x = pet_geo.right() + 10
            y = pet_geo.top()
            if x + self.width() > screen.width():
                x = pet_geo.left() - self.width() - 10
            if y + self.height() > screen.height():
                y = screen.height() - self.height()
            self.move(max(0, x), max(0, y))

    def get_custom_dance(self):
        """返回 ("play", poses, loops) 或 ("save", poses, _) 或 None。"""
        self._position_near_parent()
        self.exec()
        return self._result


class DanceMixin:
    """跳舞功能混入类，为 DesktopPet 提供跳舞状态机。"""

    _DANCE_POSES = ["dance1", "dance2", "dance3", "dance4", "dance5", "dance6"]
    _DANCE_SEQUENCE = ["cute", "win", "paper", "draw"]

    # ============================== 入口 ==============================

    def _start_dance(self):
        """右键菜单入口：弹出跳舞模式选择对话框，返回时回到上一级。"""
        while True:
            dialog = DanceSelectorDialog(self)
            choice = dialog.get_choice()
            if choice == "random":
                self._start_random_dance()
                break
            elif choice == "saved":
                if not self._show_saved_dances():
                    break
            elif choice == "custom":
                if not self._start_custom_dance():
                    break
            else:
                break

    # ============================== 模式 A：随机跳舞 ==============================

    def _start_random_dance(self):
        """从 6 个动作中随机选 4 个，循环 3 次。"""
        poses = random.sample(self._DANCE_POSES, 4)
        self._play_dance_sequence(poses, 3)

    # ============================== 模式 B：已保存的舞蹈 ==============================

    def _show_saved_dances(self):
        """显示已保存的舞蹈列表（翻页式）。返回 True 回到选择器，False 表示已播放。"""
        dances = self._load_saved_dances()
        if not dances:
            dialog = QDialog(self)
            dialog.setWindowTitle("提示")
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
                    font-size: 14px;
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
            lay = QVBoxLayout(dialog)
            lay.setContentsMargins(30, 30, 30, 30)
            msg = QLabel("主人，您没有给女仆酱定制舞蹈呦")
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setStyleSheet("font-size: 15px; color: #FF1493; font-weight: bold;")
            lay.addWidget(msg)
            btn_ok = QPushButton("知道了")
            btn_ok.clicked.connect(dialog.accept)
            lay.addWidget(btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)
            dialog.setFixedSize(300, 160)
            pet_geo = self.frameGeometry()
            screen = QGuiApplication.primaryScreen().size()
            x = pet_geo.right() + 10
            y = pet_geo.top()
            if y + dialog.height() > screen.height():
                y = screen.height() - dialog.height()
            dialog.move(max(0, x), max(0, y))
            dialog.exec()
            return True

        back_to_selector = [True]
        current_idx = [0]

        dialog = QDialog(self)
        dialog.setWindowTitle("已保存的舞蹈")
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
                font-size: 14px;
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
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("选择要播放的舞蹈：")
        title.setStyleSheet("font-size: 14px; color: #FF1493; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 舞蹈内容显示区
        dance_info = QLabel()
        dance_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dance_info.setStyleSheet("font-size: 13px; color: #8B4513; padding: 15px;"
                                 "background: white; border-radius: 6px;"
                                 "border: 1px solid #FFB6C1;")
        dance_info.setWordWrap(True)
        layout.addWidget(dance_info)

        # 页码指示
        page_label = QLabel()
        page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_label.setStyleSheet("font-size: 12px; color: #999;")
        layout.addWidget(page_label)

        # 左右翻页按钮
        nav_layout = QHBoxLayout()
        btn_prev = QPushButton("◀")
        btn_next = QPushButton("▶")
        for b in (btn_prev, btn_next):
            b.setFixedWidth(50)
        nav_layout.addStretch()
        nav_layout.addWidget(btn_prev)
        nav_layout.addWidget(btn_next)
        nav_layout.addStretch()
        layout.addLayout(nav_layout)

        def update_display():
            dance = dances[current_idx[0]]
            poses = dance["poses"]
            loops = dance["loops"]
            names = " → ".join(p.replace("dance", "动作 ") for p in poses)
            dance_info.setText(f"舞蹈 {current_idx[0] + 1}\n{names}\n循环次数: {loops} 次")
            page_label.setText(f"第 {current_idx[0] + 1} / {len(dances)} 个")
            btn_prev.setVisible(current_idx[0] > 0)
            btn_next.setVisible(current_idx[0] < len(dances) - 1)

        btn_prev.clicked.connect(lambda: (list.__setitem__(current_idx, 0, current_idx[0] - 1), update_display())[1])
        btn_next.clicked.connect(lambda: (list.__setitem__(current_idx, 0, current_idx[0] + 1), update_display())[1])

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_play = QPushButton("播放")
        btn_delete = QPushButton("删除")
        btn_back = QPushButton("返回")
        btn_back.setStyleSheet("""
            QPushButton {
                padding: 6px 14px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: white;
                color: #999;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #F5F5F5;
            }
        """)
        btn_play.clicked.connect(
            lambda: self._on_saved_play(dialog, current_idx, dances, back_to_selector))
        btn_delete.clicked.connect(
            lambda: self._on_saved_delete(dialog, current_idx, dances, update_display))
        btn_back.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_play)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_back)
        layout.addLayout(btn_layout)

        update_display()
        dialog.setFixedSize(340, 320)
        pet_geo = self.frameGeometry()
        screen = QGuiApplication.primaryScreen().size()
        x = pet_geo.right() + 10
        y = pet_geo.top()
        if y + dialog.height() > screen.height():
            y = screen.height() - dialog.height()
        dialog.move(max(0, x), max(0, y))
        dialog.exec()
        return back_to_selector[0]

    def _on_saved_play(self, dialog, current_idx, dances, back_to_selector):
        idx = current_idx[0]
        if 0 <= idx < len(dances):
            back_to_selector[0] = False
            dialog.accept()
            dance = dances[idx]
            self._play_dance_sequence(dance["poses"], dance["loops"])

    def _on_saved_delete(self, dialog, current_idx, dances, update_display):
        idx = current_idx[0]
        if 0 <= idx < len(dances):
            dances.pop(idx)
            self._save_saved_dances(dances)
            if not dances:
                dialog.close()
                return
            if current_idx[0] >= len(dances):
                current_idx[0] = len(dances) - 1
            update_display()

    # ============================== 模式 C：自定义编舞 ==============================

    def _start_custom_dance(self):
        """打开自定义编舞对话框。返回 True 回到选择器，False 表示已播放。"""
        dialog = DanceCustomizeDialog(self)
        result = dialog.get_custom_dance()
        if result:
            action, poses, loops = result
            if action == "play":
                self._play_dance_sequence(poses, loops)
                return False
            elif action == "save":
                self._save_new_dance(poses, loops)
                d = QDialog(self)
                d.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
                d.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
                d.setStyleSheet("QDialog { background: #FFF0F5; border: 2px solid #FF69B4; border-radius: 12px; } QPushButton { padding: 8px 24px; border: 1px solid #FF69B4; border-radius: 6px; background: white; color: #FF69B4; font-size: 13px; } QPushButton:hover { background: #FFE4EC; } QLabel { color: #8B4513; font-size: 14px; }")
                lay = QVBoxLayout(d)
                lay.setContentsMargins(30, 30, 30, 30)
                lbl = QLabel("主人，女仆酱已经记住这个舞蹈啦")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setStyleSheet("font-size: 15px; color: #FF1493; font-weight: bold;")
                lay.addWidget(lbl)
                ok_btn = QPushButton("好的")
                ok_btn.clicked.connect(d.accept)
                lay.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)
                d.setFixedSize(300, 160)
                pet_geo = self.frameGeometry()
                screen = QGuiApplication.primaryScreen().size()
                d.move(min(pet_geo.right() + 10, screen.width() - d.width()),
                       min(pet_geo.top(), screen.height() - d.height()))
                d.exec()
                return True
        return True  # 取消也回到选择器

    def _save_new_dance(self, poses, loops=3):
        """保存舞蹈（含循环次数）到已保存列表（最多 3 个）。"""
        dances = self._load_saved_dances()
        dances.append({"poses": poses, "loops": loops})
        if len(dances) > 3:
            dances.pop(0)
        self._save_saved_dances(dances)

    # ============================== 通用播放器 ==============================

    def _play_dance_sequence(self, poses, loops):
        """通用：播放指定动作序列，循环指定次数。"""
        self._dance_active = True
        self._dance_poses = poses
        self._dance_loops = loops
        self._dance_step = 0
        self._idle_timer.stop()
        self._state_timer.stop()
        self._change_state(poses[0])
        self._state_timer.start(1_000)

    def _on_dance_step(self):
        """跳舞步进：推进到序列下一步或结束。"""
        if not self._dance_active:
            return
        self._dance_step += 1
        total = len(self._dance_poses) * self._dance_loops
        if self._dance_step < total:
            state = self._dance_poses[self._dance_step % len(self._dance_poses)]
            self._change_state(state)
            self._state_timer.start(1_000)
        else:
            self._end_dance()

    def _end_dance(self):
        """结束跳舞，回到 stand。"""
        self._dance_active = False
        self._change_state("stand")
        self._idle_timer.start(600_000)

    # ============================== 配置存储 ==============================

    def _load_saved_dances(self):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            dances = data.get("saved_dances", [])
            # 向后兼容：旧格式是纯列表，转为 dict
            return [
                {"poses": d, "loops": 3} if isinstance(d, list) else d
                for d in dances
            ]
        except (json.JSONDecodeError, OSError):
            return []

    def _save_saved_dances(self, dances):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["saved_dances"] = dances
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass
