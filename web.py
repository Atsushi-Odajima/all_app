"""All/App Web公開版ランチャー — 外出先からもアプリを使えるようにする

仕組み:
  PC上のモバイルサーバー (mobile.py と同じもの) を Cloudflare Tunnel 経由で
  インターネットに公開する。データはPCのSQLiteのまま、HTTPSの公開URLが
  無料で発行される (Cloudflareアカウント不要のクイックトンネル)。

セキュリティ:
  - アクセスには8桁PINが必要 (~/.allapp/mobile_pin.txt、起動画面に表示)
  - URLは起動のたびに変わるランダムな trycloudflare.com サブドメイン
  - PCの電源が入っている間だけアクセス可能

初回起動時のみ、Cloudflare公式のトンネルクライアント (cloudflared.exe) を
GitHubの公式リリースから tools/ にダウンロードする。

起動:  python web.py   (または run_web.bat)
"""
import re
import socket
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from allapp.config import DATA_DIR
from allapp.webapp import app, get_pin, lan_ip

PORT = 8787
TOOLS_DIR = Path(__file__).parent / "tools"
CLOUDFLARED = TOOLS_DIR / "cloudflared.exe"
CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    "cloudflared-windows-amd64.exe"
)


def _progress(blocks: int, block_size: int, total: int) -> None:
    if total > 0:
        pct = min(100, blocks * block_size * 100 // total)
        mb = blocks * block_size / 1048576
        print(f"\r  ダウンロード中... {pct}% ({mb:.0f}MB)",
              end="", flush=True)


def ensure_cloudflared() -> None:
    if CLOUDFLARED.exists():
        return
    print("初回セットアップ: Cloudflare Tunnel クライアントを取得します")
    print(f"  取得元: {CLOUDFLARED_URL}")
    print("  (Cloudflare公式のGitHubリリースです。60MB程度)", flush=True)
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CLOUDFLARED.with_suffix(".download")
    try:
        urllib.request.urlretrieve(CLOUDFLARED_URL, tmp, reporthook=_progress)
    except Exception as e:
        print(f"\n  ダウンロードに失敗しました: {e}")
        print("  ネット接続を確認してもう一度起動してください")
        raise SystemExit(1)
    tmp.rename(CLOUDFLARED)
    print("\n  ダウンロード完了\n")


def show_qr(url: str) -> None:
    """公開URLのQRコードをPNGで保存して既定ビューアで開く"""
    try:
        import os

        import segno

        qr_path = DATA_DIR / "access_qr.png"
        segno.make(url).save(str(qr_path), scale=8, border=2)
        os.startfile(qr_path)  # noqa: S606 (自PCの画像を開くだけ)
        print(f"  QRコード: {qr_path} (画像が開きます。iPhoneカメラで読取)")
    except Exception:
        pass  # QRは補助機能なので失敗しても続行


def run_server() -> None:
    app.run(host="127.0.0.1", port=PORT, threaded=True)


def _cleanup_stale() -> None:
    """前回の残骸 (生き残ったトンネルプロセス) を掃除する。

    ウィンドウを×ボタンで閉じるとPythonだけ死んでcloudflaredが残り、
    古い無効なURLのトンネルが漂い続けるため、起動時に必ず一掃する。
    """
    subprocess.run(
        ["taskkill", "/F", "/IM", "cloudflared.exe"],
        capture_output=True,
    )


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    ensure_cloudflared()
    _cleanup_stale()

    if _port_in_use(PORT):
        print("既にAll/Appサーバーが起動しています。")
        print("先に他の黒いウィンドウ (run_web.bat / run_mobile.bat) を"
              "閉じてから、もう一度起動してください。")
        input("Enterキーで終了...")
        return

    # Flaskサーバーをバックグラウンドで起動
    threading.Thread(target=run_server, daemon=True).start()

    print("トンネルを開いています... (10秒ほどかかります)", flush=True)
    proc = subprocess.Popen(
        [str(CLOUDFLARED), "tunnel", "--no-autoupdate",
         "--url", f"http://127.0.0.1:{PORT}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    url = None
    try:
        for line in proc.stdout:
            if url is None:
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m:
                    url = m.group(0)
                    print()
                    print("=" * 56)
                    print("  All/App Web版 公開中!")
                    print(f"  外出先からのURL: {url}")
                    print(f"  ログインPIN:     {get_pin()}")
                    print()
                    print(f"  自宅Wi-Fiからは: http://{lan_ip()}:{PORT}")
                    print()
                    print("  ※URLは起動のたびに変わります")
                    print("  ※このウィンドウを閉じると公開は停止します")
                    print("=" * 56)
                    print("", flush=True)
                    show_qr(url)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
