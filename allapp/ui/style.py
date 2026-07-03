"""白基調のアプリ全体スタイル (QSS)"""

APP_STYLE = """
QMainWindow, QWidget {
    background: #ffffff;
    color: #1a1a1a;
    font-size: 13px;
}
QToolBar {
    background: #ffffff;
    border-bottom: 1px solid #e8e8e8;
    spacing: 6px;
    padding: 4px 8px;
}
QStatusBar {
    background: #fafafa;
    border-top: 1px solid #e8e8e8;
    color: #666666;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    padding: 5px 12px;
}
QPushButton:hover { background: #f5f5f5; }
QPushButton:pressed { background: #ececec; }
QPushButton:disabled { color: #aaaaaa; border-color: #eeeeee; }
QPushButton#primary {
    background: #111111;
    color: #ffffff;
    border: 1px solid #111111;
}
QPushButton#primary:hover { background: #333333; }
QPushButton#navBtn {
    border: none;
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 14px;
}
QPushButton#navBtn:hover { background: #f0f0f0; }
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {
    background: #ffffff;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #d0e3ff;
    selection-color: #1a1a1a;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
    border: 1px solid #888888;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d9d9d9;
    selection-background-color: #f0f0f0;
    selection-color: #1a1a1a;
}
QTabWidget::pane {
    border: 1px solid #e8e8e8;
    border-radius: 4px;
    top: -1px;
}
QTabBar::tab {
    background: #fafafa;
    border: 1px solid #e8e8e8;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 14px;
    margin-right: 2px;
    color: #666666;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #111111;
    font-weight: bold;
}
QTableWidget {
    gridline-color: #f0f0f0;
    border: 1px solid #e8e8e8;
    border-radius: 4px;
}
QTableWidget::item:selected {
    background: #f0f6ff;
    color: #1a1a1a;
}
QHeaderView::section {
    background: #fafafa;
    border: none;
    border-bottom: 1px solid #e8e8e8;
    border-right: 1px solid #f0f0f0;
    padding: 5px;
    font-weight: bold;
}
QListWidget {
    border: 1px solid #e8e8e8;
    border-radius: 4px;
}
QListWidget::item { padding: 4px; }
QListWidget::item:selected {
    background: #f0f6ff;
    color: #1a1a1a;
}
QSplitter::handle { background: #f0f0f0; }
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #d9d9d9;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
}
QScrollBar::handle:horizontal {
    background: #d9d9d9;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QLabel#panelTitle {
    font-size: 15px;
    font-weight: bold;
    padding: 2px 0;
}
QLabel#subtle { color: #777777; }
QFrame#trendCard {
    background: #fafafa;
    border: 1px solid #e8e8e8;
    border-radius: 8px;
}
QMessageBox { background: #ffffff; }
"""
