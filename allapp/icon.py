"""アプリアイコン: ★を逆さにした (下向きの) 星をコードで描画する"""
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap


def _star_path(cx: float, cy: float, outer: float, inner: float,
               inverted: bool = True) -> QPainterPath:
    """5点星のパスを作る。inverted=True で下向き (逆さ星)"""
    # 通常の★は頂点が真上 (-90°)。逆さ星は頂点が真下 (+90°) に来る。
    start_deg = 90.0 if inverted else -90.0
    path = QPainterPath()
    for i in range(10):
        radius = outer if i % 2 == 0 else inner
        deg = start_deg + i * 36.0
        rad = math.radians(deg)
        pt = QPointF(cx + radius * math.cos(rad), cy + radius * math.sin(rad))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    return path


def make_star_pixmap(size: int = 256, color: str = "#111111") -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    outer = size * 0.44
    inner = outer * 0.42
    path = _star_path(size / 2, size / 2, outer, inner, inverted=True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPath(path)
    painter.end()
    return pm


def make_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(make_star_pixmap(size))
    return icon
