"""All/App エントリポイント

起動:  python main.py   (または run.bat)
"""
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from allapp.icon import make_app_icon
from allapp.ui.main_window import MainWindow
from allapp.ui.style import APP_STYLE


def main() -> int:
    QApplication.setApplicationName("All/App")
    QApplication.setOrganizationName("AllApp")
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    app.setWindowIcon(make_app_icon())

    window = MainWindow()
    window.show()

    # 動作確認用: ALLAPP_SMOKE=秒数 を指定すると自動終了する
    smoke = os.environ.get("ALLAPP_SMOKE")
    if smoke:
        QTimer.singleShot(int(float(smoke) * 1000), app.quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
