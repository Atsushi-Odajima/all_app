"""記事作成パネル: プラットフォーム別プロンプト生成 → AI (Claude/ChatGPT) へ"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from ..config import AI_CATEGORIES, AI_SERVICES, CHATGPT_URL, CLAUDE_URL, Platform
from ..database import Database
from ..prompts import CONTENT_TYPES, build_prompt


class ComposerPanel(QWidget):
    open_url_requested = Signal(str)

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.platform: Platform | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.header = QLabel("記事作成")
        self.header.setObjectName("panelTitle")
        layout.addWidget(self.header)

        hint = QLabel(
            "ネタと種類を選んでプロンプトを生成 → AIボタンで開き、"
            "貼り付けて仕上げます (コピーは自動)"
        )
        hint.setWordWrap(True)
        hint.setObjectName("subtle")
        layout.addWidget(hint)

        self.topic_edit = QLineEdit()
        self.topic_edit.setPlaceholderText("ネタ・テーマ (ネタ収集から取込も可)")
        layout.addWidget(self.topic_edit)

        row = QHBoxLayout()
        self.type_combo = QComboBox()
        self.type_combo.addItems(CONTENT_TYPES)
        row.addWidget(QLabel("種類:"))
        row.addWidget(self.type_combo, 1)
        layout.addLayout(row)

        aff_row = QHBoxLayout()
        self.affiliate_edit = QLineEdit()
        self.affiliate_edit.setPlaceholderText("アフィリエイトURL (任意)")
        self.link_combo = QComboBox()
        self.link_combo.setMinimumWidth(130)
        self.link_combo.currentIndexChanged.connect(self._on_link_selected)
        aff_row.addWidget(self.affiliate_edit, 3)
        aff_row.addWidget(self.link_combo, 2)
        layout.addLayout(aff_row)
        self.reload_links()

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("ターゲット・補足 (任意)")
        layout.addWidget(self.notes_edit)

        gen_btn = QPushButton("プロンプトを生成")
        gen_btn.setObjectName("primary")
        gen_btn.clicked.connect(self._generate)
        layout.addWidget(gen_btn)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.preview = QPlainTextEdit()
        self.preview.setPlaceholderText("ここに生成されたプロンプトが表示されます")
        splitter.addWidget(self.preview)

        drafts_box = QWidget()
        dv = QVBoxLayout(drafts_box)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(4)
        dv.addWidget(QLabel("下書き (ダブルクリックで読込)"))
        self.drafts_list = QListWidget()
        self.drafts_list.itemDoubleClicked.connect(self._load_draft)
        dv.addWidget(self.drafts_list)
        splitter.addWidget(drafts_box)
        splitter.setSizes([300, 140])
        layout.addWidget(splitter, 1)

        btns = QHBoxLayout()
        copy_btn = QPushButton("コピー")
        copy_btn.clicked.connect(self._copy)
        claude_btn = QPushButton("Claudeで作成")
        claude_btn.clicked.connect(
            lambda: self._open_ai(CLAUDE_URL))
        gpt_btn = QPushButton("ChatGPTで作成")
        gpt_btn.clicked.connect(
            lambda: self._open_ai(CHATGPT_URL))
        save_btn = QPushButton("下書き保存")
        save_btn.clicked.connect(self._save_draft)
        del_btn = QPushButton("下書き削除")
        del_btn.clicked.connect(self._delete_draft)
        for b in (copy_btn, claude_btn, gpt_btn, save_btn, del_btn):
            btns.addWidget(b)
        layout.addLayout(btns)

        # その他の生成AI (画像・動画・音楽含む)
        ai_row = QHBoxLayout()
        self.ai_combo = QComboBox()
        for cat in AI_CATEGORIES:
            for svc in AI_SERVICES:
                if svc.category == cat:
                    self.ai_combo.addItem(f"[{cat}] {svc.name}", svc.url)
        ai_open_btn = QPushButton("選択したAIで作成")
        ai_open_btn.clicked.connect(self._open_selected_ai)
        ai_row.addWidget(self.ai_combo, 2)
        ai_row.addWidget(ai_open_btn, 1)
        layout.addLayout(ai_row)

    # ---------------------------------------------------------------
    def set_platform(self, platform: Platform) -> None:
        self.platform = platform
        self.header.setText(f"{platform.name} 向け記事作成")
        self._reload_drafts()

    def set_topic(self, topic: str) -> None:
        self.topic_edit.setText(topic)

    def _generate(self) -> None:
        if not self.platform:
            return
        prompt = build_prompt(
            self.platform.id,
            self.platform.name,
            self.type_combo.currentText(),
            self.topic_edit.text(),
            self.affiliate_edit.text(),
            self.notes_edit.text(),
            category=self.platform.category,
        )
        self.preview.setPlainText(prompt)

    def _copy(self) -> bool:
        text = self.preview.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "All/App",
                                    "先にプロンプトを生成してください")
            return False
        QGuiApplication.clipboard().setText(text)
        return True

    def _open_ai(self, url: str) -> None:
        if self._copy():
            self.open_url_requested.emit(url)

    def _open_selected_ai(self) -> None:
        url = self.ai_combo.currentData()
        if url:
            self._open_ai(url)

    # ------------------------------------------- アフィリエイトリンク集
    def reload_links(self) -> None:
        """アフィリエイトパネルで登録されたリンク集を読み込む"""
        self.link_combo.blockSignals(True)
        self.link_combo.clear()
        self.link_combo.addItem("リンク集から選択…", "")
        for row in self.db.list_affiliate_links():
            label = row["name"]
            if row["asp"]:
                label += f" ({row['asp']})"
            self.link_combo.addItem(label, row["url"])
        self.link_combo.blockSignals(False)

    def _on_link_selected(self, index: int) -> None:
        url = self.link_combo.itemData(index)
        if url:
            self.affiliate_edit.setText(url)

    def _save_draft(self) -> None:
        if not self.platform:
            return
        body = self.preview.toPlainText().strip()
        if not body:
            return
        title = self.topic_edit.text().strip() or body.splitlines()[0][:30]
        self.db.add_draft(self.platform.id, title, body)
        self._reload_drafts()

    def _reload_drafts(self) -> None:
        self.drafts_list.clear()
        if not self.platform:
            return
        for row in self.db.list_drafts(self.platform.id):
            item = QListWidgetItem(f"{row['created_at']}  {row['title']}")
            item.setData(0x0100, row["id"])
            self.drafts_list.addItem(item)

    def _load_draft(self, item: QListWidgetItem) -> None:
        row = self.db.get_draft(item.data(0x0100))
        if row:
            self.preview.setPlainText(row["body"])
            self.topic_edit.setText(row["title"])

    def _delete_draft(self) -> None:
        item = self.drafts_list.currentItem()
        if not item:
            return
        self.db.delete_draft(item.data(0x0100))
        self._reload_drafts()
