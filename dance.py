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
        self._result = ("save", poses, 0)
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
        """显示已保存的舞蹈列表。返回 True 回到选择器，False 表示已播放。"""
        dances = self._load_saved_dances()
        if not dances:
            msg = QMessageBox(self)
            msg.setWindowTitle("提示")
            msg.setText("还没有保存的舞蹈哦，请先在定制舞蹈中保存吧 (｡•́︿•̀｡)")
            msg.exec()
            return True  # 返回选择器

        back_to_selector = [True]

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
            QLabel, QListWidget {
                color: #8B4513;
                font-size: 13px;
            }
            QListWidget {
                border: 1px solid #FFB6C1;
                border-radius: 6px;
                background: white;
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

        label = QLabel("选择要播放的舞蹈：")
        label.setStyleSheet("font-size: 14px; color: #FF1493; font-weight: bold;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        list_widget = QListWidget()
        for idx, dance in enumerate(dances):
            names = [p.replace("dance", "动作 ") for p in dance]
            item = QListWidgetItem(f"舞蹈 {idx + 1}: {' → '.join(names)}")
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()
        btn_play = QPushButton("播放选中")
        btn_delete = QPushButton("删除选中")
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
            lambda: self._on_saved_play(dialog, list_widget, dances, back_to_selector))
        btn_delete.clicked.connect(
            lambda: self._on_saved_delete(list_widget, dances))
        btn_back.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_play)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_back)
        layout.addLayout(btn_layout)

        dialog.setFixedSize(340, 320)
        pet_geo = self.frameGeometry()
        screen = QGuiApplication.primaryScreen().size()
        x = pet_geo.right() + 10
        y = pet_geo.top()
        if x + dialog.width() > screen.width():
            x = pet_geo.left() - dialog.width() - 10
        if y + dialog.height() > screen.height():
            y = screen.height() - dialog.height()
        dialog.move(max(0, x), max(0, y))
        dialog.exec()
        return back_to_selector[0]

    def _on_saved_play(self, dialog, list_widget, dances, back_to_selector):
        row = list_widget.currentRow()
        if row >= 0 and row < len(dances):
            back_to_selector[0] = False
            dialog.accept()
            self._play_dance_sequence(dances[row], 3)

    def _on_saved_delete(self, list_widget, dances):
        row = list_widget.currentRow()
        if row >= 0 and row < len(dances):
            dances.pop(row)
            self._save_saved_dances(dances)
            list_widget.takeItem(row)

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
                self._save_new_dance(poses)
                QMessageBox.information(self, "提示", "舞蹈已保存！")
                return True
        return True  # 取消也回到选择器

    def _save_new_dance(self, poses):
        """保存舞蹈到已保存列表（最多 3 个）。"""
        dances = self._load_saved_dances()
        dances.append(poses)
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
            return data.get("saved_dances", [])
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
