"""All/Agent 安定公開版ランチャー — Tailscaleで固定URLのHTTPS公開

web.py (Cloudflareクイックトンネル) との違い:
  - URLが毎回変わらない (https://<PC名>.<tailnet>.ts.net で固定)
  - あなたのTailscaleアカウントにログインした端末だけがアクセスできる
    (PIN認証と合わせて二重の守り)
  - トンネルプロセスの常駐が不要 (Tailscaleサービスが面倒を見る)

前提 (最初の1回だけ):
  1. PCとiPhoneに Tailscale をインストールして同じアカウントでログイン
  2. Tailscale Serve の有効化 (未有効なら起動時に案内URLが表示される)

起動:  python stable.py   (または run_stable.bat / run_all.bat)
"""
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from allapp.config import DATA_DIR
from allapp.webapp import app, get_pin, lan_ip

PORT = 8787
TAILSCALE = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"


def _ts(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    # serve未有効時に有効化待ちで無限ブロックするためタイムアウト必須
    return subprocess.run(
        [TAILSCALE, *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def tailscale_dnsname() -> str | None:
    """このPCのtailnet上の固定ホスト名 (例 odaji-m.tail226869.ts.net)"""
    try:
        res = _ts("status", "--json")
        if res.returncode != 0:
            return None
        data = json.loads(res.stdout)
        if data.get("BackendState") != "Running":
            return None
        return (data.get("Self", {}).get("DNSName") or "").rstrip(".") or None
    except Exception:
        return None


def enable_serve() -> tuple[bool, str]:
    """tailscale serve を設定する。(成功したか, 案内メッセージ)"""
    try:
        res = _ts("serve", "--bg", str(PORT))
    except subprocess.TimeoutExpired as e:
        # 未有効のtailnetでは有効化案内を出したまま待ち続けるので、
        # タイムアウト時は出力から案内URLを拾ってHTTP版に切り替える
        out = ((e.stdout or b"").decode("utf-8", "replace")
               if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return False, out.strip()
    out = (res.stdout or "") + (res.stderr or "")
    if res.returncode == 0 and "not enabled" not in out.lower():
        return True, ""
    return False, out.strip()


def show_qr(url: str) -> None:
    try:
        import os

        import segno

        qr_path = DATA_DIR / "access_qr.png"
        segno.make(url).save(str(qr_path), scale=8, border=2)
        os.startfile(qr_path)  # noqa: S606 (自PCの画像を開くだけ)
        print(f"  QRコード: {qr_path} (画像が開きます。iPhoneカメラで読取)")
    except Exception:
        pass  # QRは補助機能なので失敗しても続行


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def run_server() -> None:
    # 0.0.0.0 バインド: serve未有効時でもtailnet IP/LAN経由で届くように
    app.run(host="0.0.0.0", port=PORT, threaded=True)


def main() -> None:
    if not Path(TAILSCALE).exists():
        print("Tailscaleが見つかりません。https://tailscale.com/download から")
        print("インストールしてログインした後、もう一度起動してください。")
        input("Enterキーで終了...")
        return

    if _port_in_use(PORT):
        print("既にAll/Agentサーバーが起動しています。")
        print("先に他の黒いウィンドウ (run_*.bat) を閉じてから、"
              "もう一度起動してください。")
        input("Enterキーで終了...")
        return

    dnsname = tailscale_dnsname()
    if dnsname is None:
        print("Tailscaleが未ログインか停止中です。")
        print("タスクトレイのTailscaleアイコンからログインしてください。")
        input("Enterキーで終了...")
        return

    threading.Thread(target=run_server, daemon=True).start()

    ok, note = enable_serve()
    print()
    print("=" * 60)
    if ok:
        url = f"https://{dnsname}"
        print("  All/Agent 安定公開版 稼働中! (URLは今後ずっと固定)")
        print(f"  iPhoneで開く: {url}")
    else:
        url = f"http://{dnsname}:{PORT}"
        print("  All/Agent 稼働中 (HTTP版)")
        print(f"  iPhoneで開く: {url}")
        print()
        print("  ※HTTPSの固定URLにするには、下のURLをPCのブラウザで開いて")
        print("    Tailscale Serve を有効化してください (最初の1回だけ):")
        for line in note.splitlines():
            if "https://" in line:
                print(f"    {line.strip()}")
    print(f"  ログインPIN: {get_pin()}")
    print(f"  自宅Wi-Fiからは: http://{lan_ip()}:{PORT}")
    print()
    print("  ※iPhone側はTailscaleアプリをONにしておくこと")
    print("  ※このウィンドウを閉じると停止します")
    print("=" * 60)
    print("", flush=True)
    show_qr(url)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
