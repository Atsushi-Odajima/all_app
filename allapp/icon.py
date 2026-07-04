"""アプリアイコン: 白地に ✲ (中心の開いた6本腕アスタリスク) をコードで描画する"""
import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap

# ✲ の形状パラメータ (外径=1.0 とした比率)
_INNER = 0.30   # 腕の付け根の半径 (ここが空く=オープンセンター)
_MID = 0.55     # 腕が最も太くなる位置の半径
_TIP = 1.0      # 腕の先端
_SPREAD_DEG = 13.0  # 腕の太さ (中間点の開き角)


def _asterisk_path(cx: float, cy: float, outer: float) -> QPainterPath:
    """✲ のパスを作る。6本の腕 (凧形) を60°間隔で配置、中心は開ける"""
    path = QPainterPath()
    for i in range(6):
        deg = -90.0 + i * 60.0  # 1本目は真上
        arm = []
        for r, d in ((_INNER, 0.0), (_MID, -_SPREAD_DEG),
                     (_TIP, 0.0), (_MID, _SPREAD_DEG)):
            rad = math.radians(deg + d)
            arm.append(QPointF(cx + outer * r * math.cos(rad),
                               cy + outer * r * math.sin(rad)))
        path.moveTo(arm[0])
        for pt in arm[1:]:
            path.lineTo(pt)
        path.closeSubpath()
    return path


def make_star_pixmap(size: int = 256, color: str = "#111111",
                     background: str = "#ffffff") -> QPixmap:
    """白地に✲のロゴ。background=None で透過背景"""
    pm = QPixmap(size, size)
    if background:
        pm.fill(QColor(background))
    else:
        pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = _asterisk_path(size / 2, size / 2, size * 0.42)
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
