"""実績パネル: 閲覧数・再生数・販売数などをプラットフォーム別に記録"""
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

# posts テーブルの編集可能列とDB列の対応
_COLUMNS = [
    ("title", "タイトル"),
    ("account_handle", "アカウント"),
    ("posted_at", "投稿日"),
    ("metric1", ""),  # ラベルはプラットフォーム別に差し替え
    ("metric2", ""),
    ("metric3", ""),
    ("metric4", ""),
    ("url", "URL"),
]
_METRIC_COLS = (3, 4, 5, 6)


class StatsPanel(QWidget):
    open_url_requested = Signal(str)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.platform: Platform | None = None
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.header = QLabel("実績")
        self.header.setObjectName("panelTitle")
        layout.addWidget(self.header)

        hint = QLabel("数値セルを直接編集して保存できます。URL列ダブルクリックで開きます")
        hint.setWordWrap(True)
        hint.setObjectName("subtle")
        layout.addWidget(hint)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        self.totals_label = QLabel("")
        self.totals_label.setObjectName("subtle")
        layout.addWidget(self.totals_label)

        form = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("投稿タイトル")
        self.account_edit = QLineEdit()
        self.account_edit.setPlaceholderText("アカウント")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("投稿URL (任意)")
        add_btn = QPushButton("投稿を記録")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_post)
        del_btn = QPushButton("削除")
        del_btn.clicked.connect(self._delete_selected)
        form.addWidget(self.title_edit, 3)
        form.addWidget(self.account_edit, 2)
        form.addWidget(self.url_edit, 2)
        form.addWidget(add_btn, 1)
        form.addWidget(del_btn, 1)
        layout.addLayout(form)

    # ---------------------------------------------------------------
    def set_platform(self, platform: Platform) -> None:
        self.platform = platform
        self.header.setText(f"{platform.name} の実績")
        labels = [label for _, label in _COLUMNS]
        for i, metric_label in zip(_METRIC_COLS, platform.metrics):
            labels[i] = metric_label
        self.table.setHorizontalHeaderLabels(labels)
        self.reload()

    def reload(self) -> None:
        if not self.platform:
            return
        self._loading = True
        rows = self.db.list_posts(self.platform.id)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, (col, _) in enumerate(_COLUMNS):
                value = row[col]
                item = QTableWidgetItem(str(value if value is not None else ""))
                item.setData(0x0100, row["id"])
                self.table.setItem(r, c, item)
        self._loading = False
        self._update_totals(rows)

    def _update_totals(self, rows) -> None:
        if not self.platform:
            return
        totals = [sum(row[f"metric{i}"] or 0 for row in rows)
                  for i in range(1, 5)]
        parts = [f"{label}: {total:,}"
                 for label, total in zip(self.platform.metrics, totals)]
        self.totals_label.setText(
            f"合計 ({len(rows)}件) ― " + " / ".join(parts))

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._loading or not self.platform:
            return
        item = self.table.item(row, col)
        if item is None:
            return
        post_id = item.data(0x0100)
        column = _COLUMNS[col][0]
        value = item.text().strip()
        if col in _METRIC_COLS:
            try:
                value = int(value.replace(",", "") or 0)
            except ValueError:
                QMessageBox.warning(self, "All/App", "数値を入力してください")
                self.reload()
                return
        self.db.update_post_field(post_id, column, value)
        self._update_totals(self.db.list_posts(self.platform.id))

    def _on_double_click(self, row: int, col: int) -> None:
        if _COLUMNS[col][0] != "url":
            return
        item = self.table.item(row, col)
        if item and item.text().startswith("http"):
            self.open_url_requested.emit(item.text())

    def _add_post(self) -> None:
        if not self.platform:
            return
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.information(self, "All/App",
                                    "投稿タイトルを入力してください")
            return
        self.db.add_post(
            self.platform.id, title,
            self.account_edit.text().strip(),
            self.url_edit.text().strip(),
        )
        self.title_edit.clear()
        self.url_edit.clear()
        self.reload()

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        ret = QMessageBox.question(
            self, "All/App", f"「{item.text()}」の記録を削除しますか？")
        if ret == QMessageBox.StandardButton.Yes:
            self.db.delete_post(item.data(0x0100))
            self.reload()
