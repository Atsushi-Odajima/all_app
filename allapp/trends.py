"""ネタ収集: 各プラットフォームでバズっている「投稿そのもの」を上位5件取得する

APIキー不要の公開ページのみを利用する。取得できないプラットフォームは
ok=False の結果を返し、UI側でトレンドページを開くフォールバックを表示する。

実装メモ (2026-07 時点の各サイト仕様):
- X: Yahoo!リアルタイム検索の埋め込みJSON (__NEXT_DATA__) から実際の投稿を
  取得し、いいね+RTのエンゲージメント順に上位を出す。キーワード未指定時は
  getdaytrends.com のトレンド1位をキーワードとして使う
- YouTube: 急上昇ページは廃止済みのため、Google Trends 日本の急上昇ワードを
  シードに「今週アップロード×再生数順」の検索結果から抽出する
- ニコニコ: ランキングページ埋め込みの server-response JSON を利用
- Instagram / Threads / Pinterest 等: キーワード必須。DuckDuckGo検索で
  そのプラットフォームの投稿URLに絞って上位を取得する
"""
import html as html_mod
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

from .config import CHROME_UA, PLATFORM_BY_ID, Platform

HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}
TIMEOUT = 15
MAX_ITEMS = 5  # 表示する上位件数

# YouTube検索フィルタ「今週 + 再生数順」(protobufエンコード済み)
_YT_SP_WEEK_VIEWS = "CAMSBAgDEAE%3D"


@dataclass
class TrendItem:
    title: str
    url: str
    metric: str  # 「12.3万回再生 / 1日前」等の表示用文字列


@dataclass
class TrendResult:
    platform_id: str
    ok: bool
    items: list[TrendItem] = field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------- 共通
def _parse_view_count(text: str) -> int:
    """「12.3万 回視聴」「1,234回視聴」等を数値化する"""
    m = re.search(r"([\d,.]+)\s*(万|億)?\s*回", text)
    if not m:
        return 0
    num = float(m.group(1).replace(",", ""))
    unit = m.group(2)
    if unit == "万":
        num *= 10_000
    elif unit == "億":
        num *= 100_000_000
    return int(num)


def _parse_days_ago(text: str) -> float:
    """「3 日前」「5 時間前」等を経過日数に変換 (不明時は大きい値)"""
    m = re.search(r"(\d+)\s*(分|時間|日|週間|か月|年)前", text)
    if not m:
        return 999.0
    n = int(m.group(1))
    per_day = {"分": 1 / 1440, "時間": 1 / 24, "日": 1,
               "週間": 7, "か月": 30, "年": 365}
    return n * per_day.get(m.group(2), 999)


def _google_trends_top_word() -> str:
    """Google Trends 日本の急上昇ワード1位を取得 (YouTube検索のシード用)"""
    r = requests.get(
        "https://trends.google.co.jp/trending/rss?geo=JP",
        headers=HEADERS, timeout=TIMEOUT,
    )
    r.raise_for_status()
    root = ET.fromstring(r.content)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if title:
            return title
    raise RuntimeError("Google Trendsから急上昇ワードを取得できませんでした")


def _walk_video_renderers(node, found: list) -> None:
    if isinstance(node, dict):
        if "videoRenderer" in node:
            found.append(node["videoRenderer"])
        for v in node.values():
            _walk_video_renderers(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk_video_renderers(v, found)


# ---------------------------------------------------------------- YouTube
def fetch_youtube(platform: Platform, query: str = "") -> TrendResult:
    seed_note = ""
    q = query.strip()
    if not q:
        q = _google_trends_top_word()
        seed_note = f"急上昇ワード「{q}」で検索 / "
    r = requests.get(
        f"https://www.youtube.com/results?search_query={quote(q)}"
        f"&sp={_YT_SP_WEEK_VIEWS}&hl=ja&gl=JP",
        headers=HEADERS, timeout=TIMEOUT,
    )
    r.raise_for_status()
    m = re.search(r"var ytInitialData = (\{.+?\});</script>", r.text, re.S)
    if not m:
        raise RuntimeError("検索結果を解析できませんでした")
    renderers: list = []
    _walk_video_renderers(json.loads(m.group(1)), renderers)

    videos = []
    seen = set()
    for v in renderers:
        vid = v.get("videoId")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        title = "".join(
            run.get("text", "") for run in
            v.get("title", {}).get("runs", [])
        )
        views_text = v.get("viewCountText", {}).get("simpleText", "")
        published = v.get("publishedTimeText", {}).get("simpleText", "")
        videos.append({
            "title": title, "vid": vid,
            "views": _parse_view_count(views_text),
            "published": published,
            "days": _parse_days_ago(published),
        })

    # 条件: 投稿3日以内かつ10万再生以上を優先、足りなければ再生数順で補完
    hot = [v for v in videos if v["days"] <= 3 and v["views"] >= 100_000]
    hot.sort(key=lambda v: v["views"], reverse=True)
    if len(hot) < MAX_ITEMS:
        rest = sorted(
            (v for v in videos if v not in hot),
            key=lambda v: v["views"], reverse=True,
        )
        hot.extend(rest)
    items = [
        TrendItem(
            title=v["title"],
            url=f"https://www.youtube.com/watch?v={v['vid']}",
            metric=f"{v['views']:,}回再生 / {v['published'] or '投稿日不明'}",
        )
        for v in hot[:MAX_ITEMS]
    ]
    if not items:
        raise RuntimeError("条件に合う動画が見つかりませんでした")
    return TrendResult(
        platform.id, True, items,
        note=f"{seed_note}今週アップロード×再生数順の上位 (3日以内10万再生を優先)",
    )


# ---------------------------------------------------------------- X
def _yahoo_page_data(url: str) -> dict:
    """Yahoo!リアルタイム検索ページの埋め込みJSON (__NEXT_DATA__) を取り出す"""
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
        r.text, re.S,
    )
    if not m:
        raise RuntimeError("リアルタイム検索の解析に失敗しました")
    return json.loads(m.group(1))["props"]["pageProps"]["pageData"]


def _top_x_trend() -> str:
    """日本のXトレンド1位のワードを取得 (Yahoo公式→getdaytrendsの順で試す)"""
    try:
        top = _yahoo_page_data("https://search.yahoo.co.jp/realtime")
        items = top.get("buzzTrend", {}).get("items", [])
        if items and items[0].get("query"):
            return items[0]["query"]
    except Exception:
        pass
    from bs4 import BeautifulSoup

    r = requests.get("https://getdaytrends.com/japan/",
                     headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for row in soup.select("table tbody tr"):
        link = row.select_one("a.string, td.main a")
        if link and link.get_text(strip=True):
            return link.get_text(strip=True)
    raise RuntimeError("トレンドワードを取得できませんでした")


def _ago(epoch: int) -> str:
    """UNIX時刻を「N分前/N時間前」表記にする"""
    diff = max(0, int(time.time()) - epoch)
    if diff < 3600:
        return f"{diff // 60}分前"
    if diff < 86400:
        return f"{diff // 3600}時間前"
    return f"{diff // 86400}日前"


def _clean_tweet_text(text: str) -> str:
    """検索ハイライトのマーカー等を除去する"""
    text = text.replace("\tSTART\t", "").replace("\tEND\t", "")
    return re.sub(r"\s+", " ", text).strip()


def _tweet_to_post(e: dict) -> dict | None:
    text = _clean_tweet_text(e.get("displayTextBody")
                             or e.get("displayText") or "")
    url = (e.get("url") or "").split("?")[0]
    if not text:
        return None
    if not url and e.get("id"):
        url = f"https://x.com/i/status/{e['id']}"
    if not url:
        return None
    likes = int(e.get("likesCount") or 0)
    rts = int(e.get("rtCount") or 0)
    return {
        "id": e.get("id") or url,
        "text": text,
        "url": url,
        "name": e.get("name") or "",
        "screen": e.get("screenName") or "",
        "likes": likes,
        "rts": rts,
        "score": likes + rts * 2,
        "at": int(e.get("createdAt") or 0),
    }


def fetch_x(platform: Platform, query: str = "") -> TrendResult:
    """Yahoo!リアルタイム検索(話題順)から実際にバズっているX投稿を取得する"""
    seed_note = ""
    q = query.strip()
    if not q:
        q = _top_x_trend()
        seed_note = f"トレンド1位「{q}」/ "

    # md=h = 「話題順」。反響の大きい実投稿が上位に並ぶ
    page = _yahoo_page_data(
        "https://search.yahoo.co.jp/realtime/search?p=" + quote(q) + "&md=h")

    posts: list[dict] = []
    seen: set = set()

    def add(e: dict) -> None:
        p = _tweet_to_post(e)
        if p and p["id"] not in seen:
            seen.add(p["id"])
            posts.append(p)

    # 1. ベストポスト (Yahooが選ぶ最注目投稿) を最優先
    best = page.get("bestTweet")
    if isinstance(best, dict):
        add(best)
    # 2. 話題順タイムライン
    for e in page.get("timeline", {}).get("entry", []):
        add(e)
    # ベスト投稿以外はエンゲージメント順 (いいね + RT×2) に並べ直す
    head, rest = posts[:1], posts[1:]
    rest.sort(key=lambda p: p["score"], reverse=True)
    posts = head + rest

    # 3. それでも足りなければ「人気のポスト」枠で補完
    if len(posts) < MAX_ITEMS:
        for it in page.get("poptw", {}).get("items", []):
            tid = it.get("tweetId")
            body = _clean_tweet_text(it.get("body") or "")
            if tid and body and tid not in seen:
                seen.add(tid)
                posts.append({
                    "id": tid, "text": body,
                    "url": f"https://x.com/i/status/{tid}",
                    "name": "", "screen": "",
                    "likes": -1, "rts": -1, "score": 0, "at": 0,
                })

    items = []
    for p in posts[:MAX_ITEMS]:
        who = f"{p['name']}(@{p['screen']}): " if p["screen"] else ""
        if p["likes"] >= 0:
            metric = (f"いいね {p['likes']:,} / RT {p['rts']:,}"
                      + (f" / {_ago(p['at'])}" if p["at"] else ""))
        else:
            metric = "人気のポスト (Yahoo!リアルタイム検索選出)"
        items.append(TrendItem(
            title=(who + p["text"])[:110],
            url=p["url"],
            metric=metric,
        ))
    if not items:
        raise RuntimeError(f"「{q}」の投稿が見つかりませんでした")
    return TrendResult(
        platform.id, True, items,
        note=f"{seed_note}バズ投稿 上位{len(items)}件 "
             "(Yahoo!リアルタイム検索・話題順)",
    )


# ------------------------------------------ キーワード投稿検索 (DDG)
# プラットフォームごとの (検索対象ドメイン, 投稿URLに含まれるパス)
DDG_SITES: dict[str, tuple[str, tuple]] = {
    "instagram": ("instagram.com", ("/p/", "/reel/")),
    "threads": ("threads.com", ("/post/",)),
    "pinterest": ("pinterest.com", ("/pin/",)),
    "tiktok": ("tiktok.com", ("/video/",)),
    "linevoom": ("voom.line.me", ("/post/",)),
    "note": ("note.com", ("/n/",)),
    "medium": ("medium.com", ()),
    "substack": ("substack.com", ("/p/",)),
    "fc2blog": ("blog.fc2.com", ()),
    "booth": ("booth.pm", ("/items/",)),
    "coconala": ("coconala.com", ("/services/",)),
    "brain": ("brain-market.com", ()),
    "tips": ("tips.jp", ()),
    "rumble": ("rumble.com", ()),
    "dailymotion": ("dailymotion.com", ("/video/",)),
    "fanbox": ("fanbox.cc", ("/posts/",)),
    "fantia": ("fantia.jp", ("/posts/",)),
    "cien": ("ci-en.net", ()),
    "patreon": ("patreon.com", ("/posts/",)),
}


def _ddg_real_url(href: str) -> str:
    """DuckDuckGoのリダイレクトURLから実URLを取り出す"""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return href


def _snippet_metric(snippet: str, rank: int) -> str:
    """スニペットからいいね/コメント数を抽出して指標文字列を作る"""
    m = re.search(r"([\d,]+)\s*likes?(?:,\s*([\d,]+)\s*comments?)?",
                  snippet, re.I)
    if m:
        metric = f"いいね {m.group(1)}"
        if m.group(2):
            metric += f" / コメント {m.group(2)}"
        return metric
    return f"検索上位 {rank}位"


def _search_yahoo(site_q: str) -> list[tuple[str, str, str]]:
    """Yahoo! JAPAN検索の結果を (タイトル, URL, 概要) で返す"""
    from bs4 import BeautifulSoup

    r = requests.get(
        "https://search.yahoo.co.jp/search?p=" + quote(site_q),
        headers=HEADERS, timeout=TIMEOUT,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for a in soup.select("a.sw-Card__titleInner"):
        url = a.get("href", "")
        if not url.startswith("http"):
            continue
        title = a.get_text(" ", strip=True)
        # リンク文字列に混ざる表示用URLやサイト名の残骸を除去
        title = re.sub(r"https?://\S.*$", "", title).strip()
        snippet = ""
        card = a.find_parent(class_="sw-CardBase")
        if card:
            el = card.find(class_="sw-Card__summary")
            if el:
                snippet = el.get_text(" ", strip=True)
        results.append((title, url, snippet))
    return results


def _search_ddg(site_q: str) -> list[tuple[str, str, str]]:
    """DuckDuckGo検索の結果を (タイトル, URL, 概要) で返す (予備エンジン)"""
    from bs4 import BeautifulSoup

    r = requests.get(
        f"https://html.duckduckgo.com/html/?q={quote(site_q)}&kl=jp-jp",
        headers=HEADERS, timeout=TIMEOUT,
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for res in soup.select(".result"):
        classes = " ".join(res.get("class") or [])
        if "result--ad" in classes or "sponsored" in classes:
            continue
        a = res.select_one(".result__a")
        if a is None:
            continue
        url = _ddg_real_url(a.get("href", ""))
        if not url.startswith("http") or "duckduckgo.com" in url:
            continue
        snippet_el = res.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        results.append((a.get_text(strip=True), url, snippet))
    return results


def fetch_keyword_posts(platform: Platform, query: str = "") -> TrendResult:
    """Web検索 (Yahoo→DDGの順) でプラットフォーム内の投稿を上位5件取得する"""
    q = query.strip()
    if not q:
        return TrendResult(
            platform.id, False,
            note="このプラットフォームはキーワード検索型です。\n"
                 "上の欄にキーワードを入れて「更新」を押してください。",
        )
    domain, markers = DDG_SITES[platform.id]
    accept = (domain, "threads.net") if platform.id == "threads" else (domain,)
    site_q = f"site:{domain} {q}"

    def in_domain(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host == d or host.endswith("." + d) for d in accept)

    results: list[tuple[str, str, str]] = []
    for engine in (_search_yahoo, _search_ddg):
        try:
            results = [(t, u, s) for t, u, s in engine(site_q)
                       if in_domain(u)]
        except Exception:
            results = []
        if results:
            break

    matched: list[TrendItem] = []
    others: list[TrendItem] = []
    for title, url, snippet in results:
        # 「Instagram」だけのような無意味なタイトルは概要で置き換える
        if snippet and (len(title) < 16 or title.lower() in
                        (platform.name.lower(), domain.split(".")[0])):
            title = snippet
        rank = len(matched) + len(others) + 1
        item = TrendItem(
            title=title[:100] or url,
            url=url,
            metric=_snippet_metric(snippet, rank),
        )
        # 投稿URL (例: /p/ /post/ /pin/) を優先し、それ以外は補欠にする
        if not markers or any(mk in url for mk in markers):
            matched.append(item)
        else:
            others.append(item)
        if len(matched) >= MAX_ITEMS:
            break
    items = (matched + others)[:MAX_ITEMS]
    if not items:
        raise RuntimeError(
            f"「{q}」の投稿が見つかりませんでした。検索が混み合っている"
            "可能性もあるため、1分ほど待つか別のキーワードでお試しください")
    return TrendResult(
        platform.id, True, items,
        note=f"「{q}」の{platform.name}投稿・人気アカウント "
             f"上位{len(items)}件 (Web検索)",
    )


# ---------------------------------------------------------------- ニコニコ
def fetch_niconico(platform: Platform, query: str = "") -> TrendResult:
    r = requests.get(
        "https://www.nicovideo.jp/ranking/genre/all?term=24h",
        headers=HEADERS, timeout=TIMEOUT,
    )
    r.raise_for_status()
    m = re.search(r'name="server-response"\s+content="([^"]+)"', r.text)
    if not m:
        raise RuntimeError("ランキングデータが見つかりませんでした")
    data = json.loads(html_mod.unescape(m.group(1)))
    ranking = (
        data.get("data", {})
        .get("response", {})
        .get("$getTeibanRanking", {})
        .get("data", {})
        .get("items", [])
    )
    items: list[TrendItem] = []
    for i, video in enumerate(ranking[:MAX_ITEMS]):
        count = video.get("count", {})
        items.append(TrendItem(
            title=str(video.get("title", ""))[:80],
            url=f"https://www.nicovideo.jp/watch/{video.get('id', '')}",
            metric=(
                f"24hランキング {i + 1}位 / "
                f"{count.get('view', 0):,}再生 / "
                f"{count.get('comment', 0):,}コメント"
            ),
        ))
    if not items:
        raise RuntimeError("ランキングを解析できませんでした")
    return TrendResult(platform.id, True, items,
                       note="ニコニコ動画 24時間総合ランキングより")


FETCHERS = {
    "youtube": fetch_youtube,
    "x": fetch_x,
    "niconico": fetch_niconico,
}
# キーワード検索型 (DDG) のプラットフォームを登録
for _pid in DDG_SITES:
    FETCHERS.setdefault(_pid, fetch_keyword_posts)


def query_mode(platform_id: str) -> str:
    """キーワード欄の扱い: optional=任意 / required=必須 / none=不要"""
    if platform_id in ("x", "youtube"):
        return "optional"  # 空ならトレンドワードを自動使用
    if platform_id in DDG_SITES:
        return "required"
    return "none"


def fetch_trends(platform_id: str, query: str = "") -> TrendResult:
    """トレンドを取得する。失敗・未対応時は ok=False を返す (例外は投げない)"""
    platform = PLATFORM_BY_ID[platform_id]
    fetcher = FETCHERS.get(platform_id)
    if fetcher is None:
        return TrendResult(
            platform_id, False,
            note="このプラットフォームは自動取得に未対応です。\n"
                 "下のボタンからトレンドページを開いて手動で確認してください。",
        )
    try:
        return fetcher(platform, query)
    except Exception as e:  # ネットワーク断・サイト構造変更などは全て握る
        return TrendResult(
            platform_id, False,
            note=f"自動取得に失敗しました ({type(e).__name__}: {e})\n"
                 "下のボタンからトレンドページを開いて手動で確認してください。",
        )
