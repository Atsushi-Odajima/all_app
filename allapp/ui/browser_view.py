"""アプリ内ブラウザ: プラットフォーム別の永続プロファイルでログインを保持する"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QDialog, QVBoxLayout

from ..config import CHROME_UA, PROFILES_DIR


def make_profile(profile_id: str, parent) -> QWebEngineProfile:
    """プラットフォームごとに独立した永続プロファイルを作る。

    Cookie・ローカルストレージ・キャッシュを ~/.allapp/profiles/<id>/ に
    保存するため、一度手動ログインすればアプリ再起動後もログインが保持される。
    """
    profile = QWebEngineProfile(f"allapp-{profile_id}", parent)
    base: Path = PROFILES_DIR / profile_id
    (base / "storage").mkdir(parents=True, exist_ok=True)
    (base / "cache").mkdir(parents=True, exist_ok=True)
    profile.setPersistentStoragePath(str(base / "storage"))
    profile.setCachePath(str(base / "cache"))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
    )
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    # QtWebEngine標準UAだとGoogle等がログインを拒否するためChrome相当のUAにする
    profile.setHttpUserAgent(CHROME_UA)
    profile.downloadRequested.connect(_on_download)
    return profile


def _on_download(item: QWebEngineDownloadRequest) -> None:
    item.setDownloadDirectory(str(Path.home() / "Downloads"))
    item.accept()


class BrowserView(QWebEngineView):
    """OAuthポップアップ (別ウィンドウでのログイン) にも対応したWebビュー"""

    def __init__(self, profile: QWebEngineProfile, parent=None):
        super().__init__(parent)
        page = QWebEnginePage(profile, self)
        self.setPage(page)
        self._popups: list[QDialog] = []

    def createWindow(self, _type):  # noqa: N802 (Qt override)
        # ログイン時のポップアップウィンドウ等を同じプロファイルで開く
        dialog = QDialog(self.window())
        dialog.setWindowTitle("All/Agent - ポップアップ")
        dialog.resize(520, 680)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        view = BrowserView(self.page().profile(), dialog)
        layout.addWidget(view)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.destroyed.connect(
            lambda: self._popups.remove(dialog)
            if dialog in self._popups else None
        )
        self._popups.append(dialog)
        dialog.show()
        return view
