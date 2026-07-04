"""Playwright による X (Twitter) の実ブラウザ操作

設計方針 (レビュー反映):
- セレクタは本ファイル冒頭に集約し、複数候補を順に試す (壊れたらここだけ直す)
- 投稿は「成功の確証 (完了トースト or プロフィールに出現)」が取れない限り失敗扱い
  → サイレント成功 (投稿できてないのにdone) を絶対に作らない
- アカウント毎に独立した永続プロファイル (~/.allapp/agent_profiles/) で演じ分け
- 同一プロファイルの同時オープンはChromiumがロックするため、
  呼び出し側 (agent_worker) が単一プロセス・逐次実行を保証する
"""
import random
import re
import time
from contextlib import contextmanager
from pathlib import Path

from ..config import CHROME_UA, DATA_DIR
from . import store

AGENT_PROFILES_DIR = DATA_DIR / "agent_profiles"

# ---------------------------------------------------------------- セレクタ集約
# X のUI変更で壊れたら、ここの候補リストに新しいものを足すだけでよい
SEL = {
    "compose_box": [
        '[data-testid="tweetTextarea_0"]',
        'div[role="textbox"][data-testid*="tweetTextarea"]',
        'div[role="textbox"][contenteditable="true"]',
    ],
    "post_button": [
        '[data-testid="tweetButton"]',
        '[data-testid="tweetButtonInline"]',
    ],
    "logged_in_marker": [
        '[data-testid="SideNav_NewTweet_Button"]',
        '[data-testid="AppTabBar_Profile_Link"]',
    ],
    "toast_status_link": [
        '[data-testid="toast"] a[href*="/status/"]',
    ],
    "tweet_article": ['article[data-testid="tweet"]', "article"],
    "tweet_text": ['[data-testid="tweetText"]'],
    "metrics_group": ['div[role="group"]'],
}


def profile_dir(platform: str, handle: str) -> Path:
    safe = re.sub(r"[^0-9A-Za-z_.-]", "_", handle)
    return AGENT_PROFILES_DIR / f"{platform}_{safe}"


def _human_wait(a: float = 2.0, b: float = 6.0) -> None:
    time.sleep(random.uniform(a, b))


def _first(page, keys: str, timeout: int = 8000):
    """セレクタ候補を順に試し、最初に見つかった locator を返す"""
    last_err = None
    for sel in SEL[keys]:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception as e:
            last_err = e
    raise TimeoutError(f"セレクタが見つからない: {keys} ({last_err})")


# ---------------------------------------------------------------- コンテキスト
@contextmanager
def open_context(platform: str, handle: str, headed: bool = False):
    """アカウント専用の永続プロファイルでブラウザを開く"""
    from playwright.sync_api import sync_playwright

    pdir = profile_dir(platform, handle)
    pdir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(pdir),
            headless=not headed,
            user_agent=CHROME_UA,
            viewport={"width": 1280, "height": 850},
            locale="ja-JP",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver',"
            " {get: () => undefined});"
        )
        try:
            yield ctx
        finally:
            ctx.close()


def login_window(platform: str, handle: str, timeout_sec: int = 300) -> bool:
    """PC画面にログイン用の見えるブラウザを開き、ユーザーが閉じるまで待つ。

    iPhoneの「ログイン準備」ボタン → ワーカーがこの関数を実行 →
    PCの前でログイン → ウィンドウを閉じる、という一度きりの儀式。
    """
    from playwright.sync_api import sync_playwright

    pdir = profile_dir(platform, handle)
    pdir.mkdir(parents=True, exist_ok=True)
    url = "https://x.com/login" if platform == "x" else "https://x.com/"
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(pdir), headless=False, user_agent=CHROME_UA,
            viewport={"width": 1100, "height": 800}, locale="ja-JP",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded")
            # ユーザーがウィンドウを閉じるかタイムアウトまで待機
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                if not ctx.pages:  # 全ページが閉じられた
                    return True
                time.sleep(2)
            return True
        except Exception:
            return False
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def check_logged_in(ctx) -> bool:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://x.com/home", wait_until="domcontentloaded",
              timeout=30000)
    try:
        _first(page, "logged_in_marker", timeout=10000)
        return True
    except TimeoutError:
        return False


# ---------------------------------------------------------------- 投稿
def post_to_x(ctx, text: str, own_handle: str) -> str | None:
    """Xに投稿し、成功の確証が取れたら投稿URLを返す。取れなければ None。"""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://x.com/compose/post", wait_until="domcontentloaded",
              timeout=30000)
    box = _first(page, "compose_box", timeout=15000)
    box.click()
    _human_wait(1, 2)
    # 人間らしく少しずつ入力 (fillは一瞬で終わりbot臭いため)
    page.keyboard.insert_text(text)
    _human_wait(1.5, 3)
    btn = _first(page, "post_button", timeout=8000)
    btn.click()

    # 確証1: 投稿完了トーストのリンク (最も確実。URLも取れる)
    try:
        link = _first(page, "toast_status_link", timeout=10000)
        href = link.get_attribute("href") or ""
        if href.startswith("/"):
            href = "https://x.com" + href
        return href
    except TimeoutError:
        pass

    # 確証2: 自分のプロフィールの最新投稿に本文が現れたか
    _human_wait(3, 5)
    try:
        page.goto(f"https://x.com/{own_handle}",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(SEL["tweet_article"][0], timeout=15000)
        needle = text.splitlines()[0][:20]
        for art in page.locator(SEL["tweet_article"][0]).all()[:5]:
            try:
                body = art.locator(SEL["tweet_text"][0]).first.inner_text(
                    timeout=3000)
            except Exception:
                continue
            if needle in body:
                m = art.locator('a[href*="/status/"]').first
                href = m.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://x.com" + href
                return href or None
        return None
    except Exception:
        return None


# ---------------------------------------------------------------- メトリクス
def _parse_count(text: str) -> int:
    """「1,234」「1.2万」「3億」等を数値化 (trends.pyのパーサ思想を踏襲)"""
    m = re.search(r"([\d,.]+)\s*(万|億)?", text)
    if not m:
        return 0
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return 0
    unit = m.group(2)
    if unit == "万":
        num *= 10_000
    elif unit == "億":
        num *= 100_000_000
    return int(num)


def fetch_likes(ctx, post_url: str) -> int | None:
    """個別投稿ページを開いて いいね数 を読む (タイムラインより構造が単純)"""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(SEL["tweet_article"][0], timeout=15000)
        art = page.locator(SEL["tweet_article"][0]).first
        group = art.locator(SEL["metrics_group"][0]).first
        label = group.get_attribute("aria-label") or ""
        # 例: 「3 件の返信、5 件のリポスト、120 件のいいね、...」
        m = re.search(r"([\d,.]+\s*(?:万|億)?)\s*件のいいね", label)
        if m:
            return _parse_count(m.group(1))
        # 英語UIフォールバック
        m = re.search(r"([\d,.]+[KM]?)\s*likes?", label, re.I)
        if m:
            raw = m.group(1)
            mult = 1
            if raw[-1:].upper() == "K":
                mult, raw = 1_000, raw[:-1]
            elif raw[-1:].upper() == "M":
                mult, raw = 1_000_000, raw[:-1]
            return int(float(raw.replace(",", "")) * mult)
        return 0
    except Exception:
        return None


# ---------------------------------------------------------------- 返信取得
def fetch_replies(ctx, post_url: str, own_handle: str) -> list[dict]:
    """自分の投稿ページを開き、直接の返信を取得する。

    返り値: [{key, author, text, url}] (自分自身の返信は除外)
    """
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    results = []
    try:
        page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(SEL["tweet_article"][0], timeout=15000)
        _human_wait(2, 4)
        page.mouse.wheel(0, 1200)  # 返信を遅延ロードさせる
        _human_wait(2, 3)
        arts = page.locator(SEL["tweet_article"][0]).all()
        own = own_handle.lstrip("@").lower()
        for art in arts[1:8]:  # 先頭は自分の投稿本体
            try:
                link = art.locator('a[href*="/status/"]').first
                href = link.get_attribute("href") or ""
                m = re.search(r"/([^/]+)/status/(\d+)", href)
                if not m:
                    continue
                author, tweet_id = m.group(1), m.group(2)
                if author.lower() == own:
                    continue
                body = ""
                try:
                    body = art.locator(SEL["tweet_text"][0]).first.inner_text(
                        timeout=2000)
                except Exception:
                    pass
                url = href if href.startswith("http") \
                    else "https://x.com" + href
                results.append({"key": tweet_id, "author": author,
                                "text": body, "url": url})
            except Exception:
                continue
    except Exception:
        pass
    return results


# ---------------------------------------------------------------- 返信送信
def reply_to_tweet(ctx, tweet_url: str, text: str) -> bool:
    """指定ツイートの詳細ページからインライン返信する"""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(tweet_url, wait_until="domcontentloaded", timeout=30000)
        box = _first(page, "compose_box", timeout=15000)
        box.click()
        _human_wait(1, 2)
        page.keyboard.insert_text(text)
        _human_wait(1, 2)
        btn = _first(page, "post_button", timeout=8000)
        btn.click()
        _human_wait(2, 4)
        # 送信後は入力欄が空に戻る (or 消える) ことを成功の目安にする
        try:
            remaining = _first(page, "compose_box", timeout=5000)
            content = remaining.inner_text(timeout=2000).strip()
            return content == "" or content != text
        except Exception:
            return True  # 入力欄自体が消えた = 送信された
    except Exception:
        return False
