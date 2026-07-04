"""All/Agent モバイル版サーバー (iPhone / Android / タブレット用)

PC上で起動し、同じWi-Fi内のスマートフォンのブラウザからアクセスする。
デスクトップ版と同じSQLite・ネタ収集エンジン・プロンプト生成を共有するため、
どちらで操作してもデータは常に同期されている。

起動:  python mobile.py   (または run_mobile.bat)
"""
import secrets
import socket
import time
from datetime import timedelta
from pathlib import Path

from flask import (
    Flask,
    g,
    jsonify,
    redirect,
    request,
    send_from_directory,
    session,
)

from .config import (
    DATA_DIR,
    AI_CATEGORIES,
    AI_SERVICES,
    ASPS,
    DB_PATH,
    PLATFORM_BY_ID,
    PLATFORM_CATEGORIES,
    PLATFORMS,
)
from .database import Database
from .prompts import CONTENT_TYPES, build_prompt
from .trends import fetch_trends, query_mode
from .agent import store as agent_store
from .agent import scheduler as agent_scheduler

# AI部下のテーブルを用意 (ワーカー未起動でもUIが使えるように)
agent_store.init_schema()

STATIC_DIR = Path(__file__).parent / "web" / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")


# ------------------------------------------------------------ 認証 (PIN)
def _load_or_create(path: Path, generator) -> str:
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = generator()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return value


def get_pin() -> str:
    """アクセス用PIN。~/.allapp/mobile_pin.txt を編集すれば変更できる"""
    return _load_or_create(
        DATA_DIR / "mobile_pin.txt",
        lambda: f"{secrets.randbelow(10 ** 8):08d}",  # 8桁の数字
    )


app.secret_key = _load_or_create(
    DATA_DIR / "secret_key.txt", lambda: secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(days=90)

_fail_count = 0
_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>All/Agent - ログイン</title>
<style>
body {{ background:#fff; color:#1a1a1a; margin:0; display:flex;
  align-items:center; justify-content:center; min-height:100vh;
  font-family:-apple-system,"Hiragino Kaku Gothic ProN",sans-serif; }}
.box {{ text-align:center; padding:24px; width:280px; }}
svg {{ width:56px; height:56px; }}
input {{ width:100%; box-sizing:border-box; font-size:22px; text-align:center;
  letter-spacing:4px; border:1px solid #d9d9d9; border-radius:10px;
  padding:12px; margin:16px 0 10px; }}
button {{ width:100%; background:#111; color:#fff; border:none;
  border-radius:10px; padding:13px; font-size:15px; font-weight:600; }}
.err {{ color:#c0392b; font-size:13px; min-height:18px; }}
p {{ color:#777; font-size:13px; }}
</style></head><body>
<div class="box">
<svg viewBox="0 0 24 24"><path d="M12.0,9.0 L10.76,6.64 L12.0,2.0 L13.24,6.64 Z
 M14.6,10.5 L16.02,8.25 L20.66,7.0 L17.26,10.39 Z
 M14.6,13.5 L17.26,13.61 L20.66,17.0 L16.02,15.75 Z
 M12.0,15.0 L13.24,17.36 L12.0,22.0 L10.76,17.36 Z
 M9.4,13.5 L7.98,15.75 L3.34,17.0 L6.74,13.61 Z
 M9.4,10.5 L6.74,10.39 L3.34,7.0 L7.98,8.25 Z" fill="#111"/></svg>
<h2>All/Agent</h2>
<p>PCの起動画面に表示されているPINを入力してください</p>
<form method="post" action="/login">
<input name="pin" inputmode="numeric" autocomplete="one-time-code"
 placeholder="PIN" autofocus>
<div class="err">{error}</div>
<button type="submit">ログイン</button>
</form>
</div></body></html>"""


@app.get("/login")
def login_page():
    return _LOGIN_PAGE.format(error="")


@app.post("/login")
def login_post():
    global _fail_count
    pin = (request.form.get("pin") or "").strip()
    if secrets.compare_digest(pin, get_pin()):
        _fail_count = 0
        session.permanent = True
        session["auth"] = True
        return redirect("/")
    _fail_count += 1
    time.sleep(min(_fail_count, 10))  # 総当たり対策
    return _LOGIN_PAGE.format(error="PINが違います"), 401


@app.before_request
def require_auth():
    if request.path in ("/login",) or request.path.startswith("/static/"):
        return None
    if request.path == "/manifest.webmanifest":
        return None
    if session.get("auth"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "ログインしてください"}), 401
    # リダイレクトせずログインページをそのまま返す (200)
    return _LOGIN_PAGE.format(error="")


# ---------------------------------------------------------------- DB
def get_db() -> Database:
    """リクエストごとに接続を開く (WAL + busy_timeout で並行アクセス安全)"""
    if "db" not in g:
        g.db = Database(DB_PATH)
    return g.db


@app.teardown_appcontext
def close_db(_exc) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------- 画面
@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(STATIC_DIR, "manifest.webmanifest")


# ---------------------------------------------------------------- API
@app.get("/api/init")
def api_init():
    """アプリ初期化に必要な定義一式"""
    return jsonify({
        "categories": PLATFORM_CATEGORIES,
        "platforms": [
            {
                "id": p.id, "name": p.name, "category": p.category,
                "home_url": p.home_url,
                "trend_fallback_url": p.trend_fallback_url,
                "trend_criteria": p.trend_criteria,
                "metrics": list(p.metrics),
                "auto_trend": p.auto_trend,
                "account_url_format": p.account_url_format,
                "post_url": p.post_url or p.home_url,
                "intent_format": p.intent_format,
                "post_note": p.post_note,
                "trend_query": query_mode(p.id),
            }
            for p in PLATFORMS
        ],
        "content_types": CONTENT_TYPES,
        "ai_categories": AI_CATEGORIES,
        "ai_services": [
            {"id": s.id, "name": s.name, "url": s.url,
             "category": s.category}
            for s in AI_SERVICES
        ],
        "asps": [
            {"id": a.id, "name": a.name, "login_url": a.login_url,
             "note": a.note}
            for a in ASPS
        ],
    })


@app.get("/api/trends/<platform_id>")
def api_trends(platform_id: str):
    if platform_id not in PLATFORM_BY_ID:
        return jsonify({"error": "unknown platform"}), 404
    result = fetch_trends(platform_id, request.args.get("q", ""))
    return jsonify({
        "ok": result.ok,
        "note": result.note,
        "items": [
            {"title": i.title, "url": i.url, "metric": i.metric}
            for i in result.items
        ],
    })


@app.post("/api/prompt")
def api_prompt():
    data = request.get_json(force=True)
    platform = PLATFORM_BY_ID.get(data.get("platform_id", ""))
    if platform is None:
        return jsonify({"error": "unknown platform"}), 404
    prompt = build_prompt(
        platform.id, platform.name,
        data.get("content_type", CONTENT_TYPES[0]),
        data.get("topic", ""),
        data.get("affiliate", ""),
        data.get("notes", ""),
        category=platform.category,
    )
    return jsonify({"prompt": prompt})


# ---------------- アカウント ----------------
@app.get("/api/accounts/<platform_id>")
def api_accounts(platform_id: str):
    rows = get_db().list_accounts(platform_id)
    return jsonify([dict(r) for r in rows])


@app.post("/api/accounts/<platform_id>")
def api_accounts_add(platform_id: str):
    data = request.get_json(force=True)
    handle = (data.get("handle") or "").strip().lstrip("@")
    if not handle:
        return jsonify({"error": "handle required"}), 400
    get_db().add_account(
        platform_id, handle,
        (data.get("display_name") or "").strip(),
        (data.get("memo") or "").strip(),
    )
    return jsonify({"ok": True})


@app.delete("/api/accounts/item/<int:account_id>")
def api_accounts_delete(account_id: int):
    get_db().delete_account(account_id)
    return jsonify({"ok": True})


# ---------------- 投稿実績 ----------------
@app.get("/api/posts/<platform_id>")
def api_posts(platform_id: str):
    rows = get_db().list_posts(platform_id)
    return jsonify([dict(r) for r in rows])


@app.post("/api/posts/<platform_id>")
def api_posts_add(platform_id: str):
    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    post_id = get_db().add_post(
        platform_id, title,
        (data.get("account_handle") or "").strip(),
        (data.get("url") or "").strip(),
    )
    return jsonify({"ok": True, "id": post_id})


@app.patch("/api/posts/item/<int:post_id>")
def api_posts_update(post_id: int):
    data = request.get_json(force=True)
    column = data.get("column", "")
    value = data.get("value", "")
    if column.startswith("metric"):
        try:
            value = int(str(value).replace(",", "") or 0)
        except ValueError:
            return jsonify({"error": "数値を入力してください"}), 400
    try:
        get_db().update_post_field(post_id, column, value)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


@app.delete("/api/posts/item/<int:post_id>")
def api_posts_delete(post_id: int):
    get_db().delete_post(post_id)
    return jsonify({"ok": True})


# ---------------- 下書き ----------------
@app.get("/api/drafts/<platform_id>")
def api_drafts(platform_id: str):
    rows = get_db().list_drafts(platform_id)
    return jsonify([dict(r) for r in rows])


@app.post("/api/drafts/<platform_id>")
def api_drafts_add(platform_id: str):
    data = request.get_json(force=True)
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "body required"}), 400
    title = (data.get("title") or "").strip() or body.splitlines()[0][:30]
    get_db().add_draft(platform_id, title, body)
    return jsonify({"ok": True})


@app.delete("/api/drafts/item/<int:draft_id>")
def api_drafts_delete(draft_id: int):
    get_db().delete_draft(draft_id)
    return jsonify({"ok": True})


# ---------------- アフィリエイトリンク ----------------
@app.get("/api/links")
def api_links():
    rows = get_db().list_affiliate_links()
    return jsonify([dict(r) for r in rows])


@app.post("/api/links")
def api_links_add():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    url = (data.get("url") or "").strip()
    if not name or not url:
        return jsonify({"error": "name and url required"}), 400
    get_db().add_affiliate_link(
        (data.get("asp") or "").strip(), name, url)
    return jsonify({"ok": True})


@app.delete("/api/links/<int:link_id>")
def api_links_delete(link_id: int):
    get_db().delete_affiliate_link(link_id)
    return jsonify({"ok": True})


# ================================================================ AI部下
@app.get("/api/agent/status")
def api_agent_status():
    """ワーカー稼働状態・当日プラン・承認待ち件数 (UIが10秒毎にポーリング)"""
    return jsonify({
        "worker_online": agent_store.worker_online(),
        "has_plan": agent_store.has_plan_for_today(),
        "jobs": agent_store.jobs_today(),
        "pending_replies": len(agent_store.list_reply_candidates("pending")),
    })


@app.post("/api/agent/start_day")
def api_agent_start_day():
    """「本日の投稿作業を開始しますか？→はい」の実体"""
    if not agent_store.list_personas(enabled_only=True):
        return jsonify({"error": "有効なアカウント(ペルソナ)がありません。"
                                 "先にペルソナを追加してください"}), 400
    if agent_store.has_plan_for_today():
        return jsonify({"error": "本日のプランは作成済みです"}), 400
    result = agent_scheduler.plan_today()
    if not agent_store.worker_online():
        agent_store.log("warn",
                        "プランを作成しましたが、PCのワーカーが起動していません。"
                        "PCで run_agent.bat を起動してください")
    return jsonify({"ok": True, **result})


@app.post("/api/agent/stop")
def api_agent_stop():
    n = agent_store.cancel_pending_jobs()
    agent_store.log("warn", f"停止ボタン: 未実行のジョブ{n}件を取り消しました")
    return jsonify({"ok": True, "cancelled": n})


@app.get("/api/agent/personas")
def api_agent_personas():
    return jsonify(agent_store.list_personas())


@app.post("/api/agent/personas")
def api_agent_personas_add():
    data = request.get_json(force=True)
    handle = (data.get("handle") or "").strip().lstrip("@")
    theme = (data.get("theme") or "").strip()
    if not handle or not theme:
        return jsonify({"error": "ハンドルとテーマは必須です"}), 400
    data["handle"] = handle
    data["platform"] = data.get("platform") or "x"
    pid = agent_store.add_persona(data)
    agent_store.log("info", f"ペルソナ @{handle} を追加しました。"
                            "「ログイン準備」を実行してください")
    return jsonify({"ok": True, "id": pid})


@app.patch("/api/agent/personas/<int:persona_id>")
def api_agent_personas_update(persona_id: int):
    data = request.get_json(force=True)
    # 再有効化したら連続失敗カウントもリセットする
    if data.get("enabled"):
        data["fail_streak"] = 0
    agent_store.update_persona(persona_id, data)
    return jsonify({"ok": True})


@app.delete("/api/agent/personas/<int:persona_id>")
def api_agent_personas_delete(persona_id: int):
    agent_store.delete_persona(persona_id)
    return jsonify({"ok": True})


@app.post("/api/agent/personas/<int:persona_id>/login")
def api_agent_personas_login(persona_id: int):
    """PC画面にログイン用ブラウザを開くジョブを積む"""
    if not agent_store.worker_online():
        return jsonify({"error": "PCのワーカーが起動していません。"
                                 "先に run_agent.bat を起動してください"}), 400
    agent_store.add_job(persona_id, "login", agent_store.now_str())
    return jsonify({"ok": True,
                    "message": "PC画面にブラウザが開きます。"
                               "ログイン後、そのウィンドウを閉じてください"})


@app.get("/api/agent/replies")
def api_agent_replies():
    return jsonify(agent_store.list_reply_candidates("pending"))


@app.post("/api/agent/replies/<int:cand_id>/approve")
def api_agent_reply_approve(cand_id: int):
    data = request.get_json(silent=True) or {}
    edited = (data.get("our_reply") or "").strip() or None
    cand = agent_store.get_reply_candidate(cand_id)
    if cand is None or cand["status"] != "pending":
        return jsonify({"error": "候補が見つかりません"}), 404
    agent_store.set_reply_candidate_status(cand_id, "approved", edited)
    agent_store.add_job(cand["persona_id"], "send_reply",
                        agent_store.now_str(), payload=str(cand_id))
    return jsonify({"ok": True})


@app.post("/api/agent/replies/<int:cand_id>/reject")
def api_agent_reply_reject(cand_id: int):
    cand = agent_store.get_reply_candidate(cand_id)
    if cand:
        agent_store.set_reply_candidate_status(cand_id, "rejected")
        agent_store.mark_reply_seen(cand["persona_id"], cand["reply_key"])
    return jsonify({"ok": True})


@app.get("/api/agent/logs")
def api_agent_logs():
    return jsonify(agent_store.recent_logs(40))


@app.get("/api/agent/settings")
def api_agent_settings():
    key = agent_store.get_setting("gemini_api_key")
    return jsonify({
        "gemini_api_key_set": bool(key),
        "gemini_api_key_tail": key[-4:] if key else "",
    })


@app.post("/api/agent/settings")
def api_agent_settings_save():
    data = request.get_json(force=True)
    if "gemini_api_key" in data:
        agent_store.set_setting("gemini_api_key",
                                (data.get("gemini_api_key") or "").strip())
    return jsonify({"ok": True})


# ---------------------------------------------------------------- 起動
def lan_ip() -> str:
    """このPCのLAN内IPアドレスを取得する"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # 実際には送信しない
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main(port: int = 8787, quiet: bool = False) -> None:
    if not quiet:
        ip = lan_ip()
        print()
        print("=" * 52)
        print("  All/Agent モバイル版サーバー起動")
        print(f"  iPhoneのSafariで開く: http://{ip}:{port}")
        print("  (PCと同じWi-Fiに接続してください)")
        print(f"  ログインPIN: {get_pin()}")
        print("  ホーム画面に追加するとアプリのように使えます")
        print("=" * 52)
        print()
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
