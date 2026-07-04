"""All/Agent メインウィンドウ

上部ツールバー: ✲ロゴアイコン + プラットフォーム切替プルダウン + ブラウザ操作
左パネル: アカウント / ネタ収集 / 記事作成 / 実績 / アフィリ
右側: プラットフォーム別の永続セッション付きアプリ内ブラウザ
(AIツール用・ASP用にも独立した永続プロファイルを持つ)
"""
from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QAction, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QToolButton,
)

from ..config import (
    AI_CATEGORIES,
    AI_SERVICES,
    DB_PATH,
    PLATFORM_BY_ID,
    PLATFORM_CATEGORIES,
    PLATFORMS,
    Platform,
    ensure_dirs,
)
from ..database import Database
from ..icon import make_app_icon, make_star_pixmap
from .accounts_panel import AccountsPanel
from .affiliate_panel import AffiliatePanel
from .browser_view import BrowserView, make_profile
from .composer_panel import ComposerPanel
from .stats_panel import StatsPanel
from .trends_panel import TrendsPanel

# 補助ブラウザ (プラットフォーム外) のホームURL
_AUX_HOMES = {
    "ai-tools": "https://claude.ai/new",
    "asp": "https://www.a8.net/",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        ensure_dirs()
        self.db = Database(DB_PATH)
        self.setWindowTitle("All/Agent - マルチプラットフォーム運用管理")
        self.setWindowIcon(make_app_icon())

        # プラットフォームごとのブラウザ (遅延生成でメモリ節約。
        # 初回切替に少し時間がかかるのは仕様として許容)
        self._profiles = {}
        self._views: dict[str, BrowserView] = {}
        self._aux_views: dict[str, BrowserView] = {}  # ai-tools / asp

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._restore_geometry()

        # 初期プラットフォーム (先頭はカテゴリ見出しなので実項目を選ぶ)
        self.select_platform(PLATFORMS[0].id)

    # ------------------------------------------------------------ UI構築
    def _build_toolbar(self) -> None:
        bar = QToolBar()
        bar.setMovable(False)
        bar.setFloatable(False)
        self.addToolBar(bar)

        icon_label = QLabel()
        icon_label.setPixmap(make_star_pixmap(22))
        icon_label.setContentsMargins(4, 0, 2, 0)
        bar.addWidget(icon_label)

        title = QLabel("<b>All/Agent</b>")
        title.setContentsMargins(0, 0, 10, 0)
        bar.addWidget(title)

        # カテゴリ見出し付きプルダウン
        self.platform_combo = QComboBox()
        self.platform_combo.setMinimumWidth(190)
        model = QStandardItemModel()
        for category in PLATFORM_CATEGORIES:
            header = QStandardItem(f"── {category} ──")
            header.setEnabled(False)
            model.appendRow(header)
            for p in PLATFORMS:
                if p.category == category:
                    item = QStandardItem(p.name)
                    item.setData(p.id, Qt.ItemDataRole.UserRole)
                    model.appendRow(item)
        self.platform_combo.setModel(model)
        self.platform_combo.setMaxVisibleItems(24)
        self.platform_combo.currentIndexChanged.connect(
            self._on_platform_changed)
        bar.addWidget(self.platform_combo)

        def nav_btn(text: str, tooltip: str, slot) -> QPushButton:
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            btn.setToolTip(tooltip)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
            return btn

        nav_btn("←", "戻る", lambda: self._current_view()
                and self._current_view().back())
        nav_btn("→", "進む", lambda: self._current_view()
                and self._current_view().forward())
        nav_btn("⟳", "再読み込み", lambda: self._current_view()
                and self._current_view().reload())
        nav_btn("⌂", "ホーム", self._go_home)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("URL")
        self.url_edit.returnPressed.connect(self._navigate_from_bar)
        bar.addWidget(self.url_edit)

        ai_claude = QPushButton("Claude")
        ai_claude.setToolTip("Claudeをアプリ内ブラウザで開く (記事作成用)")
        ai_claude.clicked.connect(
            lambda: self.open_url("https://claude.ai/new", target="ai-tools"))
        bar.addWidget(ai_claude)

        ai_gpt = QPushButton("ChatGPT")
        ai_gpt.setToolTip("ChatGPTをアプリ内ブラウザで開く (記事作成用)")
        ai_gpt.clicked.connect(
            lambda: self.open_url("https://chatgpt.com/", target="ai-tools"))
        bar.addWidget(ai_gpt)

        # その他の生成AI (文章/画像/動画/音楽) のメニュー
        ai_menu_btn = QToolButton()
        ai_menu_btn.setText("AI一覧 ▾")
        ai_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(ai_menu_btn)
        for cat in AI_CATEGORIES:
            section = menu.addMenu(cat)
            for svc in AI_SERVICES:
                if svc.category != cat:
                    continue
                action = QAction(svc.name, menu)
                action.triggered.connect(
                    lambda _=False, url=svc.url:
                    self.open_url(url, target="ai-tools"))
                section.addAction(action)
        ai_menu_btn.setMenu(menu)
        bar.addWidget(ai_menu_btn)

        back_platform = QPushButton("SNSに戻る")
        back_platform.setToolTip("AI・ASP画面からプラットフォーム画面に戻る")
        back_platform.clicked.connect(self._back_to_platform)
        bar.addWidget(back_platform)

    def _build_central(self) -> None:
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左: 機能パネル
        self.tabs = QTabWidget()
        self.accounts_panel = AccountsPanel(self.db)
        self.trends_panel = TrendsPanel()
        self.composer_panel = ComposerPanel(self.db)
        self.stats_panel = StatsPanel(self.db)
        self.affiliate_panel = AffiliatePanel(self.db)
        self.tabs.addTab(self.accounts_panel, "アカウント")
        self.tabs.addTab(self.trends_panel, "ネタ収集")
        self.tabs.addTab(self.composer_panel, "記事作成")
        self.tabs.addTab(self.stats_panel, "実績")
        self.tabs.addTab(self.affiliate_panel, "アフィリ")

        for panel in (self.accounts_panel, self.trends_panel,
                      self.stats_panel):
            panel.open_url_requested.connect(self.open_url)
        # 記事作成のAIボタンはAIプロファイルで開く
        self.composer_panel.open_url_requested.connect(
            lambda url: self.open_url(url, target="ai-tools"))
        self.trends_panel.send_to_composer.connect(self._topic_to_composer)
        self.affiliate_panel.open_asp_requested.connect(
            lambda url: self.open_url(url, target="asp"))
        self.affiliate_panel.links_changed.connect(
            self.composer_panel.reload_links)

        # 右: ブラウザスタック
        self.browser_stack = QStackedWidget()
        placeholder = QLabel(
            "プラットフォームを選択するとここにブラウザが表示されます"
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browser_stack.addWidget(placeholder)

        self.splitter.addWidget(self.tabs)
        self.splitter.addWidget(self.browser_stack)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([400, 900])
        self.setCentralWidget(self.splitter)

    def _build_statusbar(self) -> None:
        self.statusBar().showMessage(
            f"データ保存先: {DB_PATH.parent}  |  "
            "手動ログイン方式: 各サイトに一度ログインすれば以降は保持されます"
        )

    # ------------------------------------------------------ ブラウザ管理
    def _current_platform(self) -> Platform:
        pid = self.platform_combo.currentData(Qt.ItemDataRole.UserRole)
        return PLATFORM_BY_ID.get(pid, PLATFORMS[0])

    def select_platform(self, platform_id: str) -> None:
        """プラットフォームIDでプルダウンを切り替える"""
        model = self.platform_combo.model()
        for row in range(model.rowCount()):
            item = model.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == platform_id:
                if self.platform_combo.currentIndex() == row:
                    self._on_platform_changed(row)  # 初期化時
                else:
                    self.platform_combo.setCurrentIndex(row)
                return

    def _ensure_view(self, platform: Platform) -> BrowserView:
        """プラットフォーム用ブラウザを初回アクセス時に生成 (遅延生成)"""
        if platform.id not in self._views:
            profile = make_profile(platform.id, self)
            self._profiles[platform.id] = profile
            view = BrowserView(profile, self)
            view.urlChanged.connect(self._on_url_changed)
            view.load(QUrl(platform.home_url))
            self._views[platform.id] = view
            self.browser_stack.addWidget(view)
        return self._views[platform.id]

    def _ensure_aux_view(self, name: str) -> BrowserView:
        """AIツール用・ASP用の補助ブラウザ (独立した永続プロファイル)"""
        if name not in self._aux_views:
            profile = make_profile(name, self)
            self._profiles[name] = profile
            view = BrowserView(profile, self)
            view.urlChanged.connect(self._on_url_changed)
            self._aux_views[name] = view
            self.browser_stack.addWidget(view)
        return self._aux_views[name]

    def _current_view(self) -> BrowserView | None:
        w = self.browser_stack.currentWidget()
        return w if isinstance(w, BrowserView) else None

    # -------------------------------------------------------- スロット
    def _on_platform_changed(self, _index: int) -> None:
        pid = self.platform_combo.currentData(Qt.ItemDataRole.UserRole)
        if not pid:  # カテゴリ見出し
            return
        platform = self._current_platform()
        self.setWindowTitle(f"All/Agent - {platform.name}")
        view = self._ensure_view(platform)
        self.browser_stack.setCurrentWidget(view)
        self.url_edit.setText(view.url().toString())
        for panel in (self.accounts_panel, self.trends_panel,
                      self.composer_panel, self.stats_panel,
                      self.affiliate_panel):
            panel.set_platform(platform)

    def open_url(self, url: str, target: str = "") -> None:
        """URLを開く。target: '' = 現在のプラットフォーム / 'ai-tools' / 'asp'"""
        if target:
            view = self._ensure_aux_view(target)
        else:
            view = self._ensure_view(self._current_platform())
        view.load(QUrl(url))
        self.browser_stack.setCurrentWidget(view)

    def _back_to_platform(self) -> None:
        view = self._ensure_view(self._current_platform())
        self.browser_stack.setCurrentWidget(view)
        self.url_edit.setText(view.url().toString())

    def _go_home(self) -> None:
        view = self._current_view()
        if view is None:
            return
        for name, aux in self._aux_views.items():
            if view is aux:
                view.load(QUrl(_AUX_HOMES.get(name, "https://claude.ai/new")))
                return
        view.load(QUrl(self._current_platform().home_url))

    def _navigate_from_bar(self) -> None:
        text = self.url_edit.text().strip()
        if not text:
            return
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        view = self._current_view()
        if view is None:
            view = self._ensure_view(self._current_platform())
            self.browser_stack.setCurrentWidget(view)
        view.load(QUrl(text))

    def _on_url_changed(self, url: QUrl) -> None:
        if self.sender() is self.browser_stack.currentWidget():
            self.url_edit.setText(url.toString())

    def _topic_to_composer(self, topic: str) -> None:
        self.composer_panel.set_topic(topic)
        self.tabs.setCurrentWidget(self.composer_panel)

    # ------------------------------------------------------ ウィンドウ状態
    def _restore_geometry(self) -> None:
        settings = QSettings("AllApp", "AllApp")
        geo = settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1360, 860)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        QSettings("AllApp", "AllApp").setValue(
            "geometry", self.saveGeometry())
        super().closeEvent(event)
