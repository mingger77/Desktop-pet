import random
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt


class GameMixin:
    """石头剪刀布游戏混入类。"""

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
