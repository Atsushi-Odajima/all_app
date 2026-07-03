"""アカウント一覧パネル: プラットフォームごとの運用アカウントを管理"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import Platform
from ..database import Database


class AccountsPanel(QWidget):
    open_url_requested = Signal(str)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.platform: Platform | None = None
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.header = QLabel("アカウント一覧")
        self.header.setObjectName("panelTitle")
        layout.addWidget(self.header)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ハンドル", "表示名", "メモ"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setVisible(False)
        self.table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        self.open_btn = QPushButton("プロフィールを開く")
        self.open_btn.clicked.connect(self._open_selected)
        self.delete_btn = QPushButton("削除")
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.open_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addWidget(QLabel("― アカウントを追加 ―"))
        form = QHBoxLayout()
        self.handle_edit = QLineEdit()
        self.handle_edit.setPlaceholderText("ハンドル (@なし)")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("表示名")
        add_btn = QPushButton("追加")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_account)
        form.addWidget(self.handle_edit, 2)
        form.addWidget(self.name_edit, 2)
        form.addWidget(add_btn, 1)
        layout.addLayout(form)

    # ---------------------------------------------------------------
    def set_platform(self, platform: Platform) -> None:
        self.platform = platform
        self.header.setText(f"{platform.name} のアカウント一覧")
        self.reload()

    def reload(self) -> None:
        if not self.platform:
            return
        self._loading = True
        rows = self.db.list_accounts(self.platform.id)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(("handle", "display_name", "memo")):
                item = QTableWidgetItem(row[key] or "")
                item.setData(0x0100, row["id"])  # Qt.UserRole
                self.table.setItem(r, c, item)
        self._loading = False

    def _on_cell_changed(self, row: int, _col: int) -> None:
        if self._loading or not self.platform:
            return
        id_item = self.table.item(row, 0)
        if id_item is None:
            return
        account_id = id_item.data(0x0100)
        values = [
            self.table.item(row, c).text() if self.table.item(row, c) else ""
            for c in range(3)
        ]
        self.db.update_account(account_id, *values)

    def _add_account(self) -> None:
        if not self.platform:
            return
        handle = self.handle_edit.text().strip().lstrip("@")
        if not handle:
            QMessageBox.information(self, "All/App", "ハンドルを入力してください")
            return
        self.db.add_account(
            self.platform.id, handle, self.name_edit.text().strip(), ""
        )
        self.handle_edit.clear()
        self.name_edit.clear()
        self.reload()

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            return rows[0].row()
        return self.table.currentRow()

    def _open_selected(self) -> None:
        if not self.platform:
            return
        row = self._selected_row()
        if row < 0:
            QMessageBox.information(self, "All/App", "アカウントを選択してください")
            return
        handle = self.table.item(row, 0).text()
        url = self.platform.account_url_format.format(handle=handle)
        self.open_url_requested.emit(url)

    def _delete_selected(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        item = self.table.item(row, 0)
        ret = QMessageBox.question(
            self, "All/App",
            f"アカウント「{item.text()}」を削除しますか？",
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.db.delete_account(item.data(0x0100))
            self.reload()
