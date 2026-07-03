"""All/App モバイル版サーバー起動用エントリポイント

iPhone等からの利用方法:
1. このスクリプトをPCで起動 (python mobile.py または run_mobile.bat)
2. iPhoneをPCと同じWi-Fiに接続
3. Safariで表示されたURL (http://<PCのIP>:8787) を開く
4. 共有ボタン → 「ホーム画面に追加」でアプリのように使える
"""
import sys

from allapp.webapp import main

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    main(port)
