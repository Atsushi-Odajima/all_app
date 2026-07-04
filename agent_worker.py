"""All/App AI部下ワーカー — 自動投稿・返信・バズ検知の実行体

独立した常駐プロセスとして動く (レビュー指摘 C-1 反映):
- Flask (mobile.py / web.py) はUIとして当日ジョブをDBに書くだけ
- 本ワーカーがDBのジョブキューを30秒毎にポーリングして逐次実行する
- トンネルのON/OFFやFlaskの再起動とワーカーの生死が完全に分離される

起動:  python agent_worker.py   (または run_agent.bat)
停止:  このウィンドウを閉じる (実行中ジョブは次回起動時に error 扱い)

Playwright操作はすべて本プロセスのメインスレッドで行う
(Windows + sync API はスレッド内で不安定なため / プロファイルロック回避のため逐次実行)。
"""
import sys
import time
import traceback

from allapp.agent import scheduler, store

POLL_SEC = 30


def main() -> None:
    store.init_schema()
    stuck = store.reset_stuck_jobs()
    if stuck:
        store.log("warn", f"前回中断されたジョブ{stuck}件をエラー扱いにしました")
    store.log("ok", "AI部下ワーカーを起動しました (PCオンライン)")
    print("=" * 56)
    print("  All/App AI部下ワーカー 稼働中")
    print("  iPhoneの「AI部下」タブから操作してください")
    print("  このウィンドウを閉じると自動投稿は停止します")
    print("=" * 56, flush=True)

    while True:
        store.beat_heartbeat()
        try:
            job = store.next_due_job()
        except Exception as e:
            print(f"ジョブ取得エラー: {e}", flush=True)
            time.sleep(POLL_SEC)
            continue
        if job is None:
            time.sleep(POLL_SEC)
            continue
        _run(job)


def _run(job: dict) -> None:
    print(f"[{store.now_str()}] ジョブ実行: #{job['id']} {job['kind']}",
          flush=True)
    # スリープ復帰などで期限を大きく過ぎた投稿は実行しない (凍結防止)
    if scheduler.is_stale_post(job):
        store.finish_job(job["id"], "skipped",
                         f"期限を{scheduler.STALE_POST_MIN}分以上超過")
        store.log("warn",
                  "期限を大きく過ぎた投稿ジョブをスキップしました"
                  " (PCがスリープしていた可能性)")
        return
    # 投稿は時間帯外なら実行しない
    if job["kind"] == "post":
        persona = store.get_persona(job["persona_id"])
        if persona and not scheduler.in_window(persona):
            store.finish_job(job["id"], "skipped", "投稿時間帯の外")
            return
    try:
        status, detail = scheduler.execute_job(job)
        store.finish_job(job["id"], status, detail)
    except Exception as e:
        store.finish_job(job["id"], "error", f"{type(e).__name__}: {e}")
        store.log("error",
                  f"ジョブ#{job['id']} ({job['kind']}) が異常終了:"
                  f" {type(e).__name__}")
        traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        store.log("info", "ワーカーを停止しました")
        sys.exit(0)
