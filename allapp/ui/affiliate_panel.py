"""アフィリエイトパネル: ASP管理画面への接続とアフィリエイトリンク管理

ASPへのログインは専用の永続プロファイル (asp) を使ったアプリ内ブラウザで行い、
一度ログインすれば保持される。取得したアフィリエイトリンクはここに登録して
おくと、記事作成パネルから1クリックで呼び出せる。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..config import ASPS, Platform
from ..database import Database


class AffiliatePanel(QWidget):
    open_asp_requested = Signal(str)  # ASP管理画面をaspプロファイルで開く
    links_changed = Signal()          # 記事作成パネルのリンク一覧を更新

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QLabel("アフィリエイト (ASP) 連携")
        header.setObjectName("panelTitle")
        layout.addWidget(header)

        hint = QLabel(
            "ASPにログインして案件リンクを取得 → 下のリンク集に登録すると"
            "記事作成から1クリックで使えます (ログインは保持されます)"
        )
        hint.setWordWrap(True)
        hint.setObjectName("subtle")
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ---------------- ASP一覧 ----------------
        asp_box = QWidget()
        av = QVBoxLayout(asp_box)
        av.setContentsMargins(0, 0, 0, 0)
        av.setSpacing(4)
        av.addWidget(QLabel("ASP一覧 (ダブルクリックで管理画面を開く)"))
        self.asp_list = QListWidget()
        for asp in ASPS:
            item = QListWidgetItem(f"{asp.name}  ―  {asp.note}")
            item.setData(0x0100, asp.login_url)
            item.setToolTip(asp.note)
            self.asp_list.addItem(item)
        self.asp_list.itemDoubleClicked.connect(self._open_asp_item)
        av.addWidget(self.asp_list)
        open_asp_btn = QPushButton("選択したASPの管理画面を開く")
        open_asp_btn.setObjectName("primary")
        open_asp_btn.clicked.connect(self._open_selected_asp)
        av.addWidget(open_asp_btn)
        splitter.addWidget(asp_box)

        # ------------- アフィリエイトリンク集 -------------
        links_box = QWidget()
        lv = QVBoxLayout(links_box)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        lv.addWidget(QLabel("マイリンク集 (セル編集で保存 / URLダブルクリックでコピー)"))

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["案件名", "ASP", "URL"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        lv.addWidget(self.table)

        form = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("案件名")
        self.asp_combo = QComboBox()
        self.asp_combo.addItem("(その他)")
        for asp in ASPS:
            self.asp_combo.addItem(asp.name)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("アフィリエイトURL")
        add_btn = QPushButton("登録")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_link)
        del_btn = QPushButton("削除")
        del_btn.clicked.connect(self._delete_selected)
        form.addWidget(self.name_edit, 2)
        form.addWidget(self.asp_combo, 2)
        form.addWidget(self.url_edit, 3)
        form.addWidget(add_btn, 1)
        form.addWidget(del_btn, 1)
        lv.addLayout(form)
        splitter.addWidget(links_box)

        splitter.setSizes([260, 340])
        layout.addWidget(splitter, 1)

        self.reload_links()

    # ---------------------------------------------------------------
    def set_platform(self, platform: Platform) -> None:
        """ASP連携はプラットフォーム共通のため何もしない"""

    def _open_asp_item(self, item: QListWidgetItem) -> None:
        self.open_asp_requested.emit(item.data(0x0100))

    def _open_selected_asp(self) -> None:
        item = self.asp_list.currentItem()
        if item is None:
            QMessageBox.information(self, "All/App", "ASPを選択してください")
            return
        self.open_asp_requested.emit(item.data(0x0100))

    # ---------------------------------------------------------------
    def reload_links(self) -> None:
        self._loading = True
        rows = self.db.list_affiliate_links()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(("name", "asp", "url")):
                item = QTableWidgetItem(row[key] or "")
                item.setData(0x0100, row["id"])
                self.table.setItem(r, c, item)
        self._loading = False

    def _on_cell_changed(self, row: int, _col: int) -> None:
        if self._loading:
            return
        id_item = self.table.item(row, 0)
        if id_item is None:
            return
        values = [
            self.table.item(row, c).text() if self.table.item(row, c) else ""
            for c in range(3)
        ]
        self.db.update_affiliate_link(
            id_item.data(0x0100),
            asp=values[1], name=values[0], url=values[2], memo="",
        )
        self.links_changed.emit()

    def _on_double_click(self, row: int, col: int) -> None:
        if col != 2:
            return
        item = self.table.item(row, col)
        if item and item.text():
            QGuiApplication.clipboard().setText(item.text())

    def _add_link(self) -> None:
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()
        if not name or not url:
            QMessageBox.information(
                self, "All/App", "案件名とURLを入力してください")
            return
        asp = self.asp_combo.currentText()
        if asp == "(その他)":
            asp = ""
        self.db.add_affiliate_link(asp, name, url)
        self.name_edit.clear()
        self.url_edit.clear()
        self.reload_links()
        self.links_changed.emit()

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        ret = QMessageBox.question(
            self, "All/App", f"リンク「{item.text()}」を削除しますか？")
        if ret == QMessageBox.StandardButton.Yes:
            self.db.delete_affiliate_link(item.data(0x0100))
            self.reload_links()
            self.links_changed.emit()
