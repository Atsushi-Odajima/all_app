"""ネタ収集パネル: バズっているコンテンツ上位3件を表示"""
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config import Platform
from ..trends import TrendResult, fetch_trends, query_mode


class _FetchSignals(QObject):
    finished = Signal(object)  # TrendResult


class _FetchWorker(QRunnable):
    """ネットワーク取得をバックグラウンドで行いUIを固めない"""

    def __init__(self, platform_id: str, query: str = ""):
        super().__init__()
        self.platform_id = platform_id
        self.query = query
        self.signals = _FetchSignals()

    @Slot()
    def run(self) -> None:
        # 例外は fetch_trends 内部で処理済み (ok=False で返る)
        result = fetch_trends(self.platform_id, self.query)
        self.signals.finished.emit(result)


class TrendsPanel(QWidget):
    open_url_requested = Signal(str)
    send_to_composer = Signal(str)  # ネタタイトルを記事作成パネルへ

    def __init__(self, parent=None):
        super().__init__(parent)
        self.platform: Platform | None = None
        self.pool = QThreadPool.globalInstance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.header = QLabel("ネタ収集")
        self.header.setObjectName("panelTitle")
        layout.addWidget(self.header)

        self.criteria_label = QLabel("")
        self.criteria_label.setWordWrap(True)
        self.criteria_label.setObjectName("subtle")
        layout.addWidget(self.criteria_label)

        # 検索キーワード (プラットフォームにより任意/必須)
        self.query_edit = QLineEdit()
        self.query_edit.returnPressed.connect(self.refresh)
        layout.addWidget(self.query_edit)

        top_row = QHBoxLayout()
        self.refresh_btn = QPushButton("更新 (バズ投稿 上位5件)")
        self.refresh_btn.setObjectName("primary")
        self.refresh_btn.clicked.connect(self.refresh)
        top_row.addWidget(self.refresh_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # 結果表示エリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.items_host = QWidget()
        self.items_layout = QVBoxLayout(self.items_host)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(8)
        self.items_layout.addStretch()
        scroll.setWidget(self.items_host)
        layout.addWidget(scroll, 1)

        self.fallback_btn = QPushButton("トレンドページをブラウザで開く")
        self.fallback_btn.clicked.connect(self._open_fallback)
        layout.addWidget(self.fallback_btn)

    # ---------------------------------------------------------------
    def set_platform(self, platform: Platform) -> None:
        self.platform = platform
        self.header.setText(f"{platform.name} のネタ収集")
        self.criteria_label.setText(platform.trend_criteria)
        mode = query_mode(platform.id)
        self.query_edit.setVisible(mode != "none")
        self.query_edit.clear()
        if mode == "required":
            self.query_edit.setPlaceholderText(
                "キーワード必須 (例: ダイエット、副業、猫)")
        else:
            self.query_edit.setPlaceholderText(
                "検索キーワード (空欄ならトレンド1位を自動使用)")
        self._clear_items()
        if mode == "required":
            self.status_label.setText(
                "キーワードを入れて「更新」を押すと、"
                "そのキーワードの投稿上位5件を表示します")
        elif platform.auto_trend or mode != "none":
            self.status_label.setText("「更新」で最新のバズ投稿上位5件を取得します")
        else:
            self.status_label.setText(
                "このプラットフォームは自動取得未対応です。\n"
                "下のボタンからトレンドページを開いて確認してください。"
            )

    def refresh(self) -> None:
        if not self.platform:
            return
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("取得中...")
        worker = _FetchWorker(self.platform.id, self.query_edit.text())
        worker.signals.finished.connect(self._on_result)
        self.pool.start(worker)

    def _on_result(self, result: TrendResult) -> None:
        self.refresh_btn.setEnabled(True)
        # 取得中にプラットフォームを切り替えた場合は破棄
        if not self.platform or result.platform_id != self.platform.id:
            return
        self._clear_items()
        if not result.ok:
            self.status_label.setText(result.note)
            return
        self.status_label.setText(result.note)
        for rank, item in enumerate(result.items, start=1):
            self._add_item_card(rank, item.title, item.metric, item.url)

    def _clear_items(self) -> None:
        while self.items_layout.count() > 1:
            child = self.items_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _add_item_card(self, rank: int, title: str,
                       metric: str, url: str) -> None:
        card = QFrame()
        card.setObjectName("trendCard")
        v = QVBoxLayout(card)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(4)

        title_label = QLabel(f"{rank}位  {title}")
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-weight: bold;")
        v.addWidget(title_label)

        metric_label = QLabel(metric)
        metric_label.setObjectName("subtle")
        v.addWidget(metric_label)

        btns = QHBoxLayout()
        open_btn = QPushButton("開く")
        open_btn.clicked.connect(lambda _=False, u=url:
                                 self.open_url_requested.emit(u))
        compose_btn = QPushButton("このネタで作成→")
        compose_btn.clicked.connect(lambda _=False, t=title:
                                    self.send_to_composer.emit(t))
        btns.addWidget(open_btn)
        btns.addWidget(compose_btn)
        btns.addStretch()
        v.addLayout(btns)

        self.items_layout.insertWidget(self.items_layout.count() - 1, card)

    def _open_fallback(self) -> None:
        if self.platform:
            self.open_url_requested.emit(self.platform.trend_fallback_url)
