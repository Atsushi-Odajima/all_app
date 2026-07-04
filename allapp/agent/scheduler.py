"""1日のプラン生成と、各ジョブの実行ロジック

プラン生成はFlask (UIの「はい」ボタン) から、
ジョブ実行はワーカープロセス (agent_worker.py) から呼ばれる。
"""
import random
import sqlite3
from datetime import datetime, timedelta

from ..config import DB_PATH, PLATFORM_BY_ID
from . import generator, poster, replies, store

# 期限をこれ以上過ぎた投稿ジョブは実行せず skip する
# (PCスリープ復帰時に溜まったジョブが一斉実行→凍結、を防ぐ)
STALE_POST_MIN = 45


# ---------------------------------------------------------------- プラン生成
def plan_today() -> dict:
    """有効な全ペルソナの当日ジョブを生成する。「はい」ボタンの実体。"""
    personas = store.list_personas(enabled_only=True)
    now = datetime.now()
    n_posts = n_others = 0
    for p in personas:
        times = _pick_post_times(p, now)
        for t in times:
            store.add_job(p["id"], "post", t.strftime("%Y-%m-%d %H:%M:%S"))
            n_posts += 1
        if not times:
            continue
        last_post = max(times)
        # 日付をまたぐと翌日の「プラン作成済み」誤判定になるため23:50で頭打ち
        day_end = now.replace(hour=23, minute=50, second=0, microsecond=0)
        if p["auto_reply"]:
            # 返信チェックは投稿の後に2回 (投稿が無ければ意味がない)
            for offset_min in (40, 150):
                t = min(day_end, last_post + timedelta(
                    minutes=offset_min + random.randint(0, 20)))
                store.add_job(
                    p["id"], "reply_check", t.strftime("%Y-%m-%d %H:%M:%S"))
                n_others += 1
        # バズチェックは最終投稿の2〜3時間後に1回
        t = min(day_end,
                last_post + timedelta(minutes=random.randint(120, 180)))
        store.add_job(p["id"], "buzz_check", t.strftime("%Y-%m-%d %H:%M:%S"))
        n_others += 1
    store.log("ok",
              f"本日のプランを作成: {len(personas)}アカウント / "
              f"投稿{n_posts}件 + チェック{n_others}件")
    return {"personas": len(personas), "posts": n_posts, "others": n_others}


def _pick_post_times(p: dict, now: datetime) -> list[datetime]:
    """投稿時刻を時間帯内にランダム分散させる (等間隔=bot臭を避ける)"""
    start_h = int(p["window_start"])
    end_h = int(p["window_end"])
    count = max(0, int(p["posts_per_day"]))
    if count == 0 or end_h <= start_h:
        return []
    window_start = now.replace(hour=start_h, minute=0, second=0,
                               microsecond=0)
    window_end = now.replace(hour=end_h, minute=0, second=0, microsecond=0)
    earliest = max(window_start, now + timedelta(minutes=3))
    if earliest >= window_end:
        # 今日の時間帯をもう過ぎている → 今から30分以内に1回だけ
        store.log("warn",
                  f"@{p['handle']}: 投稿時間帯({start_h}-{end_h}時)を過ぎて"
                  "いるため、今日は直近1回のみ投稿します")
        return [now + timedelta(minutes=random.randint(3, 30))]
    # 時間帯をcount等分し、各区画内でランダムにずらす
    total_sec = (window_end - earliest).total_seconds()
    slot = total_sec / count
    times = []
    for i in range(count):
        offset = slot * i + random.uniform(slot * 0.1, slot * 0.9)
        times.append(earliest + timedelta(seconds=offset))
    return times


# ---------------------------------------------------------------- 実行
def execute_job(job: dict) -> tuple[str, str]:
    """ジョブを実行し (status, detail) を返す。ワーカーから呼ばれる。"""
    persona = store.get_persona(job["persona_id"])
    if persona is None:
        return "skipped", "ペルソナが削除済み"
    kind = job["kind"]
    if kind == "login":
        return _run_login(persona)
    if not persona["enabled"] and kind != "login":
        return "skipped", "ペルソナが無効化されている"
    if kind == "post":
        return _run_post(job, persona)
    if kind == "reply_check":
        return _run_reply_check(persona)
    if kind == "buzz_check":
        return _run_buzz_check(persona)
    if kind == "send_reply":
        return _run_send_reply(job, persona)
    return "error", f"不明なジョブ種別: {kind}"


def is_stale_post(job: dict) -> bool:
    try:
        run_at = datetime.strptime(job["run_at"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return (job["kind"] == "post"
            and datetime.now() - run_at > timedelta(minutes=STALE_POST_MIN))


def in_window(persona: dict) -> bool:
    h = datetime.now().hour
    return int(persona["window_start"]) <= h < int(persona["window_end"]) + 1


# ---------------------------------------------------------------- 各ジョブ
def _run_login(persona: dict) -> tuple[str, str]:
    store.log("info",
              f"@{persona['handle']}: PC画面にログイン用ブラウザを開きます。"
              "ログイン後、ウィンドウを閉じてください (最大5分)")
    ok = poster.login_window(persona["platform"], persona["handle"])
    if ok:
        store.log("ok", f"@{persona['handle']}: ログイン準備を終了しました")
        return "done", "ログインウィンドウを閉じました"
    return "error", "ログインウィンドウの起動に失敗"


def _run_post(job: dict, persona: dict) -> tuple[str, str]:
    handle = persona["handle"]
    text, engine = generator.generate_post(persona)
    store.log("info", f"@{handle}: 投稿文を生成 ({engine}) → 投稿します")
    with poster.open_context(persona["platform"], handle) as ctx:
        if not poster.check_logged_in(ctx):
            streak = store.record_post_result(persona["id"], False)
            msg = (f"@{handle}: ログインが切れています。"
                   "「ログイン準備」をやり直してください")
            store.log("error", msg + (f" (連続失敗{streak}回)" if streak else ""))
            return "error", "ログイン切れ"
        url = poster.post_to_x(ctx, text, handle)
    if url is None:
        streak = store.record_post_result(persona["id"], False)
        if streak >= 3:
            store.log("error",
                      f"@{handle}: 投稿が3回連続で失敗したため自動停止しました。"
                      "X側のUI変更かログイン切れの可能性があります")
        else:
            store.log("error", f"@{handle}: 投稿の成功を確認できませんでした"
                               f" (連続失敗{streak}回)")
        return "error", "投稿の成功を確認できず"
    store.record_post_result(persona["id"], True)
    store.add_agent_post(persona["id"], persona["platform"], text, url)
    _add_stats_post(persona["platform"], text, handle, url)
    store.log("ok", f"@{handle}: 投稿しました → {text[:40]}…")
    return "done", url


def _run_reply_check(persona: dict) -> tuple[str, str]:
    handle = persona["handle"]
    targets = store.posts_for_reply_check(persona["id"])
    if not targets:
        return "done", "チェック対象の投稿なし"
    sent_today = store.replies_sent_today(persona["id"])
    limit = int(persona["reply_limit"])
    auto_mode = persona["reply_mode"] == "auto"
    found = replied = queued = 0
    with poster.open_context(persona["platform"], handle) as ctx:
        for post in targets:
            for r in poster.fetch_replies(ctx, post["url"], handle):
                if store.is_reply_seen(persona["id"], r["key"]):
                    continue
                found += 1
                safe, reason = replies.is_safe_to_reply(r["text"])
                if not safe:
                    store.mark_reply_seen(persona["id"], r["key"])
                    store.log("info",
                              f"@{handle}: @{r['author']}への返信をスキップ"
                              f" ({reason})")
                    continue
                if sent_today + replied >= limit:
                    store.log("warn",
                              f"@{handle}: 本日の返信上限({limit}件)に到達")
                    break
                reply_text = replies.pick_reply(persona.get("tone", ""))
                if auto_mode:
                    ok = poster.reply_to_tweet(ctx, r["url"], reply_text)
                    store.mark_reply_seen(persona["id"], r["key"])
                    if ok:
                        replied += 1
                        store.log("ok",
                                  f"@{handle}: @{r['author']}に返信"
                                  f"「{reply_text}」")
                    else:
                        store.log("warn",
                                  f"@{handle}: @{r['author']}への返信に失敗")
                else:
                    cid = store.add_reply_candidate(
                        persona["id"], r["key"], post["url"],
                        r["author"], r["text"], reply_text)
                    if cid:
                        queued += 1
    if queued:
        store.log("info",
                  f"@{handle}: 返信候補を{queued}件作成しました。"
                  "「AI部下」タブで承認してください")
    return "done", f"新着{found}件 / 返信{replied}件 / 承認待ち{queued}件"


def _run_send_reply(job: dict, persona: dict) -> tuple[str, str]:
    """承認された返信候補を送信する (payload=候補ID)"""
    try:
        cand_id = int(job["payload"])
    except (TypeError, ValueError):
        return "error", "payloadが不正"
    cand = store.get_reply_candidate(cand_id)
    if cand is None or cand["status"] != "approved":
        return "skipped", "候補が見つからないか未承認"
    tweet_url = f"https://x.com/{cand['author']}/status/{cand['reply_key']}"
    with poster.open_context(persona["platform"], persona["handle"]) as ctx:
        ok = poster.reply_to_tweet(ctx, tweet_url, cand["our_reply"])
    store.mark_reply_seen(persona["id"], cand["reply_key"])
    if ok:
        store.set_reply_candidate_status(cand_id, "sent")
        store.log("ok",
                  f"@{persona['handle']}: @{cand['author']}に返信"
                  f"「{cand['our_reply']}」")
        return "done", "返信送信"
    store.set_reply_candidate_status(cand_id, "error")
    store.log("warn", f"@{persona['handle']}: 承認済み返信の送信に失敗")
    return "error", "返信送信に失敗"


def _run_buzz_check(persona: dict) -> tuple[str, str]:
    handle = persona["handle"]
    targets = store.posts_for_buzz_check(persona["id"])
    if not targets:
        return "done", "チェック対象の投稿なし"
    threshold = int(persona["buzz_threshold"])
    cross_targets = [t.strip() for t in
                     (persona["cross_targets"] or "").split(",") if t.strip()]
    buzzed = 0
    with poster.open_context(persona["platform"], handle) as ctx:
        for post in targets:
            likes = poster.fetch_likes(ctx, post["url"])
            if likes is None:
                continue
            if likes < threshold:
                store.update_post_buzz(post["id"], likes)
                continue
            buzzed += 1
            store.update_post_buzz(post["id"], likes, cross_posted=True)
            store.log("ok",
                      f"🎉 @{handle}: バズ検知! いいね{likes}件 → "
                      f"{len(cross_targets)}プラットフォームへ横展開します")
            for target_id in cross_targets:
                platform = PLATFORM_BY_ID.get(target_id)
                if platform is None:
                    continue
                rewritten = generator.rewrite_for_platform(
                    post["text"], target_id, platform.name, persona["theme"])
                _add_draft(target_id, f"[バズ横展開] {post['text'][:25]}",
                           rewritten)
                store.log("info",
                          f"@{handle}: {platform.name}向けの下書きを保存"
                          "しました (「作成」タブ→下書きから1タップ投稿)")
    return "done", f"バズ{buzzed}件を横展開"


# ------------------------------------------------- 既存テーブルへの書き込み
def _sql(query: str, params: tuple) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute(query, params)
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _add_stats_post(platform: str, text: str, handle: str, url: str) -> None:
    """既存の実績テーブルにも記録する (実績タブに自動で並ぶ)"""
    _sql("INSERT INTO posts (platform, account_handle, title, url,"
         " posted_at, updated_at) VALUES (?,?,?,?,?,?)",
         (platform, handle, text[:50], url, _now(), _now()))


def _add_draft(platform: str, title: str, body: str) -> None:
    """既存の下書きテーブルに保存 (モバイルUIの下書き一覧に出る)"""
    _sql("INSERT INTO drafts (platform, title, body, created_at)"
         " VALUES (?,?,?,?)", (platform, title[:60], body, _now()))
