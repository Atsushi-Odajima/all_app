"""エージェント用の永続化 (ペルソナ・ジョブキュー・活動ログ・設定)

既存の allapp.sqlite3 に専用テーブルを追加する。
Flask (UI) とワーカープロセス (agent_worker.py) の両方から呼ばれるため、
呼び出しごとに接続を開閉する (WAL + busy_timeout で安全に共存)。
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from ..config import DB_PATH

# ワーカーのハートビートがこの秒数より古ければ「PCオフライン」扱い
HEARTBEAT_STALE_SEC = 90


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


@contextmanager
def _db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema() -> None:
    with _db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_personas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,          -- 現状 'x' のみ完全自動対応
                handle TEXT NOT NULL,
                theme TEXT NOT NULL,             -- 投稿テーマ (例: 節約×自炊)
                tone TEXT DEFAULT '親しみやすい', -- 口調キャラ
                posts_per_day INTEGER DEFAULT 2,
                window_start INTEGER DEFAULT 9,  -- 投稿時間帯 (時)
                window_end INTEGER DEFAULT 22,
                auto_reply INTEGER DEFAULT 1,
                reply_mode TEXT DEFAULT 'approve', -- approve=承認制 / auto=全自動
                reply_limit INTEGER DEFAULT 10,  -- 1日の返信上限
                buzz_threshold INTEGER DEFAULT 30, -- いいね数がこれ以上でバズ判定
                cross_targets TEXT DEFAULT '',   -- 横展開先 platform id (カンマ区切り)
                hashtags TEXT DEFAULT '',        -- 毎回付けるタグ (任意)
                enabled INTEGER DEFAULT 1,
                fail_streak INTEGER DEFAULT 0,   -- 投稿連続失敗数 (3でサーキットブレーカー)
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id INTEGER NOT NULL,
                kind TEXT NOT NULL,   -- post / reply_check / buzz_check / send_reply / login
                run_at TEXT NOT NULL,            -- 'YYYY-MM-DD HH:MM:SS'
                payload TEXT DEFAULT '',         -- kind依存の追加情報 (JSON等)
                status TEXT DEFAULT 'pending',   -- pending/running/done/error/skipped
                detail TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                at TEXT NOT NULL,
                level TEXT DEFAULT 'info',       -- info / ok / warn / error
                message TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_seen_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id INTEGER NOT NULL,
                reply_key TEXT NOT NULL,         -- 返信元ツイートの一意キー
                replied_at TEXT NOT NULL,
                UNIQUE(persona_id, reply_key)
            );
            CREATE TABLE IF NOT EXISTS agent_reply_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id INTEGER NOT NULL,
                reply_key TEXT NOT NULL,         -- 相手ツイートID (重複防止)
                post_url TEXT NOT NULL,          -- 自分のどの投稿への返信か
                author TEXT DEFAULT '',          -- 相手のハンドル
                their_text TEXT DEFAULT '',      -- 相手の返信本文
                our_reply TEXT NOT NULL,         -- こちらの返信案
                status TEXT DEFAULT 'pending',   -- pending/approved/sent/rejected/error
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(persona_id, reply_key)
            );
            CREATE TABLE IF NOT EXISTS agent_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                text TEXT NOT NULL,
                url TEXT DEFAULT '',
                posted_at TEXT NOT NULL,
                likes INTEGER DEFAULT 0,
                cross_posted INTEGER DEFAULT 0   -- バズ横展開済みフラグ
            );
            CREATE TABLE IF NOT EXISTS agent_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


# ---------------------------------------------------------------- 設定
def get_setting(key: str, default: str = "") -> str:
    with _db() as c:
        row = c.execute(
            "SELECT value FROM agent_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO agent_settings (key,value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ------------------------------------------------------- ハートビート
def beat_heartbeat() -> None:
    set_setting("worker_heartbeat", now_str())


def worker_online() -> bool:
    """ワーカープロセスが生きているか (iPhone UIのオンライン表示用)"""
    hb = get_setting("worker_heartbeat")
    if not hb:
        return False
    try:
        last = datetime.strptime(hb, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return (datetime.now() - last).total_seconds() < HEARTBEAT_STALE_SEC


# ---------------------------------------------------------------- ペルソナ
def list_personas(enabled_only: bool = False) -> list[dict]:
    q = "SELECT * FROM agent_personas"
    if enabled_only:
        q += " WHERE enabled=1"
    q += " ORDER BY id"
    with _db() as c:
        return [dict(r) for r in c.execute(q).fetchall()]


def get_persona(persona_id: int) -> dict | None:
    with _db() as c:
        row = c.execute(
            "SELECT * FROM agent_personas WHERE id=?", (persona_id,)
        ).fetchone()
        return dict(row) if row else None


def _to_int(value, default: int) -> int:
    """フォームから来る空文字や不正値は既定値に倒す"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def add_persona(data: dict) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO agent_personas (platform, handle, theme, tone,"
            " posts_per_day, window_start, window_end, auto_reply,"
            " reply_mode, reply_limit, buzz_threshold, cross_targets,"
            " hashtags, enabled, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (data["platform"], data["handle"].lstrip("@"), data["theme"],
             (data.get("tone") or "").strip() or "親しみやすい",
             _to_int(data.get("posts_per_day"), 2),
             _to_int(data.get("window_start"), 9),
             _to_int(data.get("window_end"), 22),
             1 if data.get("auto_reply", True) else 0,
             data.get("reply_mode", "approve"),
             _to_int(data.get("reply_limit"), 10),
             _to_int(data.get("buzz_threshold"), 30),
             data.get("cross_targets", ""),
             data.get("hashtags", ""),
             1, now_str()),
        )
        return cur.lastrowid


def update_persona(persona_id: int, data: dict) -> None:
    allowed = {"platform", "handle", "theme", "tone", "posts_per_day",
               "window_start", "window_end", "auto_reply", "reply_mode",
               "reply_limit", "buzz_threshold", "cross_targets", "hashtags",
               "enabled", "fail_streak"}
    sets, vals = [], []
    for k, v in data.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(persona_id)
    with _db() as c:
        c.execute(
            f"UPDATE agent_personas SET {', '.join(sets)} WHERE id=?", vals)


def delete_persona(persona_id: int) -> None:
    with _db() as c:
        c.execute("DELETE FROM agent_personas WHERE id=?", (persona_id,))
        c.execute("DELETE FROM agent_jobs WHERE persona_id=?", (persona_id,))


def record_post_result(persona_id: int, success: bool) -> int:
    """投稿の成否を記録し、現在の連続失敗数を返す。

    3連続失敗でペルソナを自動停止する (サーキットブレーカー)。
    セレクタ破損・ログイン切れで壊れたまま走り続けるのを防ぐ。
    """
    with _db() as c:
        if success:
            c.execute(
                "UPDATE agent_personas SET fail_streak=0 WHERE id=?",
                (persona_id,))
            return 0
        c.execute(
            "UPDATE agent_personas SET fail_streak=fail_streak+1 WHERE id=?",
            (persona_id,))
        row = c.execute(
            "SELECT fail_streak FROM agent_personas WHERE id=?",
            (persona_id,)).fetchone()
        streak = row["fail_streak"] if row else 0
        if streak >= 3:
            c.execute(
                "UPDATE agent_personas SET enabled=0 WHERE id=?",
                (persona_id,))
        return streak


# ---------------------------------------------------------------- ジョブ
def add_job(persona_id: int, kind: str, run_at: str,
            payload: str = "") -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO agent_jobs (persona_id, kind, run_at, payload,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (persona_id, kind, run_at, payload, now_str(), now_str()),
        )


def next_due_job() -> dict | None:
    """実行時刻を過ぎた pending ジョブを1件、アトミックに取り出す。

    BEGIN IMMEDIATE で書きロックを先に取り、SELECT→UPDATE の間に
    別プロセスが同じ行を掴む隙間をなくす (二重投稿防止)。
    """
    conn = sqlite3.connect(str(DB_PATH), isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM agent_jobs WHERE status='pending' AND run_at<=?"
            " ORDER BY run_at LIMIT 1", (now_str(),)
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE agent_jobs SET status='running', updated_at=? WHERE id=?",
            (now_str(), row["id"]),
        )
        conn.execute("COMMIT")
        return dict(row)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def finish_job(job_id: int, status: str, detail: str = "") -> None:
    with _db() as c:
        c.execute(
            "UPDATE agent_jobs SET status=?, detail=?, updated_at=?"
            " WHERE id=?",
            (status, detail[:500], now_str(), job_id),
        )


def jobs_today() -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT j.*, p.platform, p.handle FROM agent_jobs j"
            " LEFT JOIN agent_personas p ON p.id=j.persona_id"
            " WHERE j.run_at LIKE ? ORDER BY j.run_at",
            (today_str() + "%",),
        ).fetchall()]


def cancel_pending_jobs() -> int:
    with _db() as c:
        cur = c.execute(
            "UPDATE agent_jobs SET status='skipped', updated_at=?"
            " WHERE status='pending'", (now_str(),))
        return cur.rowcount


def has_plan_for_today() -> bool:
    with _db() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM agent_jobs WHERE run_at LIKE ?"
            " AND kind != 'login'",
            (today_str() + "%",),
        ).fetchone()
        return row["n"] > 0


def reset_stuck_jobs() -> int:
    """ワーカー起動時に、前回クラッシュ等で running のまま残った
    ジョブを error に倒す (再実行はしない: 二重投稿の方が実害が大きい)"""
    with _db() as c:
        cur = c.execute(
            "UPDATE agent_jobs SET status='error',"
            " detail='ワーカー異常終了により中断', updated_at=?"
            " WHERE status='running'", (now_str(),))
        return cur.rowcount


# ---------------------------------------------------------------- ログ
def log(level: str, message: str) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO agent_log (at, level, message) VALUES (?,?,?)",
            (now_str(), level, message[:1000]),
        )
        # 肥大化防止: 最新2000件だけ残す
        c.execute(
            "DELETE FROM agent_log WHERE id NOT IN"
            " (SELECT id FROM agent_log ORDER BY id DESC LIMIT 2000)")


def recent_logs(limit: int = 40) -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM agent_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()]


# ---------------------------------------------------------------- 返信
def is_reply_seen(persona_id: int, reply_key: str) -> bool:
    with _db() as c:
        return c.execute(
            "SELECT 1 FROM agent_seen_replies WHERE persona_id=?"
            " AND reply_key=?", (persona_id, reply_key)
        ).fetchone() is not None


def mark_reply_seen(persona_id: int, reply_key: str) -> None:
    with _db() as c:
        c.execute(
            "INSERT OR IGNORE INTO agent_seen_replies"
            " (persona_id, reply_key, replied_at) VALUES (?,?,?)",
            (persona_id, reply_key, now_str()),
        )


def replies_sent_today(persona_id: int) -> int:
    with _db() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM agent_seen_replies"
            " WHERE persona_id=? AND replied_at LIKE ?",
            (persona_id, today_str() + "%"),
        ).fetchone()
        return row["n"]


def add_reply_candidate(persona_id: int, reply_key: str, post_url: str,
                        author: str, their_text: str, our_reply: str,
                        status: str = "pending") -> int | None:
    """返信候補を登録。既知の reply_key なら None を返す"""
    with _db() as c:
        try:
            cur = c.execute(
                "INSERT INTO agent_reply_candidates (persona_id, reply_key,"
                " post_url, author, their_text, our_reply, status,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (persona_id, reply_key, post_url, author,
                 their_text[:300], our_reply, status, now_str(), now_str()),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def list_reply_candidates(status: str = "pending",
                          limit: int = 30) -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT rc.*, p.handle, p.platform FROM agent_reply_candidates rc"
            " LEFT JOIN agent_personas p ON p.id=rc.persona_id"
            " WHERE rc.status=? ORDER BY rc.id DESC LIMIT ?",
            (status, limit),
        ).fetchall()]


def get_reply_candidate(cand_id: int) -> dict | None:
    with _db() as c:
        row = c.execute(
            "SELECT * FROM agent_reply_candidates WHERE id=?", (cand_id,)
        ).fetchone()
        return dict(row) if row else None


def set_reply_candidate_status(cand_id: int, status: str,
                               our_reply: str | None = None) -> None:
    with _db() as c:
        if our_reply is None:
            c.execute(
                "UPDATE agent_reply_candidates SET status=?, updated_at=?"
                " WHERE id=?", (status, now_str(), cand_id))
        else:
            c.execute(
                "UPDATE agent_reply_candidates SET status=?, our_reply=?,"
                " updated_at=? WHERE id=?",
                (status, our_reply, now_str(), cand_id))


# ---------------------------------------------------------------- 投稿記録
def add_agent_post(persona_id: int, platform: str, text: str,
                   url: str = "") -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO agent_posts (persona_id, platform, text, url,"
            " posted_at) VALUES (?,?,?,?,?)",
            (persona_id, platform, text, url, now_str()),
        )
        return cur.lastrowid


def recent_agent_posts(persona_id: int, limit: int = 5) -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM agent_posts WHERE persona_id=?"
            " ORDER BY id DESC LIMIT ?", (persona_id, limit)
        ).fetchall()]


def posts_for_buzz_check(persona_id: int) -> list[dict]:
    """直近3日・URL付き・未横展開の自動投稿"""
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM agent_posts WHERE persona_id=? AND cross_posted=0"
            " AND url != ''"
            " AND posted_at >= datetime('now', 'localtime', '-3 days')"
            " ORDER BY id DESC LIMIT 10", (persona_id,)
        ).fetchall()]


def posts_for_reply_check(persona_id: int) -> list[dict]:
    """直近2日・URL付きの自動投稿 (返信チェック対象)"""
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM agent_posts WHERE persona_id=? AND url != ''"
            " AND posted_at >= datetime('now', 'localtime', '-2 days')"
            " ORDER BY id DESC LIMIT 5", (persona_id,)
        ).fetchall()]


def update_post_buzz(post_id: int, likes: int,
                     cross_posted: bool | None = None) -> None:
    with _db() as c:
        if cross_posted is None:
            c.execute("UPDATE agent_posts SET likes=? WHERE id=?",
                      (likes, post_id))
        else:
            c.execute(
                "UPDATE agent_posts SET likes=?, cross_posted=? WHERE id=?",
                (likes, 1 if cross_posted else 0, post_id))
