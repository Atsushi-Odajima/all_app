"""SQLiteによるアカウント・投稿実績・下書きの永続化"""
import sqlite3
from datetime import datetime
from pathlib import Path


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


class Database:
    """UIスレッドからのみ使用する前提のシンプルなDBラッパー"""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        # デスクトップ版とモバイルサーバーが同じDBを同時に使えるようにする
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                handle TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                memo TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                account_handle TEXT DEFAULT '',
                title TEXT NOT NULL,
                url TEXT DEFAULT '',
                posted_at TEXT NOT NULL,
                metric1 INTEGER DEFAULT 0,
                metric2 INTEGER DEFAULT 0,
                metric3 INTEGER DEFAULT 0,
                metric4 INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS affiliate_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asp TEXT DEFAULT '',
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                memo TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    # ---------- アカウント ----------
    def list_accounts(self, platform: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM accounts WHERE platform=? ORDER BY id",
            (platform,),
        ).fetchall()

    def add_account(self, platform: str, handle: str,
                    display_name: str, memo: str) -> None:
        self.conn.execute(
            "INSERT INTO accounts (platform, handle, display_name, memo,"
            " created_at) VALUES (?,?,?,?,?)",
            (platform, handle, display_name, memo, _now()),
        )
        self.conn.commit()

    def update_account(self, account_id: int, handle: str,
                       display_name: str, memo: str) -> None:
        self.conn.execute(
            "UPDATE accounts SET handle=?, display_name=?, memo=? WHERE id=?",
            (handle, display_name, memo, account_id),
        )
        self.conn.commit()

    def delete_account(self, account_id: int) -> None:
        self.conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        self.conn.commit()

    # ---------- 投稿実績 ----------
    def list_posts(self, platform: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM posts WHERE platform=? ORDER BY id DESC",
            (platform,),
        ).fetchall()

    def add_post(self, platform: str, title: str, account_handle: str,
                 url: str, posted_at: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO posts (platform, account_handle, title, url,"
            " posted_at, updated_at) VALUES (?,?,?,?,?,?)",
            (platform, account_handle, title, url,
             posted_at or _now(), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_post_field(self, post_id: int, column: str, value) -> None:
        allowed = {"title", "account_handle", "url", "posted_at",
                   "metric1", "metric2", "metric3", "metric4"}
        if column not in allowed:
            raise ValueError(f"invalid column: {column}")
        self.conn.execute(
            f"UPDATE posts SET {column}=?, updated_at=? WHERE id=?",
            (value, _now(), post_id),
        )
        self.conn.commit()

    def delete_post(self, post_id: int) -> None:
        self.conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
        self.conn.commit()

    # ---------- 下書き ----------
    def list_drafts(self, platform: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM drafts WHERE platform=? ORDER BY id DESC",
            (platform,),
        ).fetchall()

    def add_draft(self, platform: str, title: str, body: str) -> None:
        self.conn.execute(
            "INSERT INTO drafts (platform, title, body, created_at)"
            " VALUES (?,?,?,?)",
            (platform, title, body, _now()),
        )
        self.conn.commit()

    # ---------- アフィリエイトリンク ----------
    def list_affiliate_links(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM affiliate_links ORDER BY id DESC"
        ).fetchall()

    def add_affiliate_link(self, asp: str, name: str,
                           url: str, memo: str = "") -> None:
        self.conn.execute(
            "INSERT INTO affiliate_links (asp, name, url, memo, created_at)"
            " VALUES (?,?,?,?,?)",
            (asp, name, url, memo, _now()),
        )
        self.conn.commit()

    def update_affiliate_link(self, link_id: int, asp: str, name: str,
                              url: str, memo: str) -> None:
        self.conn.execute(
            "UPDATE affiliate_links SET asp=?, name=?, url=?, memo=?"
            " WHERE id=?",
            (asp, name, url, memo, link_id),
        )
        self.conn.commit()

    def delete_affiliate_link(self, link_id: int) -> None:
        self.conn.execute(
            "DELETE FROM affiliate_links WHERE id=?", (link_id,))
        self.conn.commit()

    def get_draft(self, draft_id: int):
        return self.conn.execute(
            "SELECT * FROM drafts WHERE id=?", (draft_id,)
        ).fetchone()

    def delete_draft(self, draft_id: int) -> None:
        self.conn.execute("DELETE FROM drafts WHERE id=?", (draft_id,))
        self.conn.commit()
