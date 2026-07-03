"""プラットフォーム・ASP・AIサービスの定義と共通設定"""
from dataclasses import dataclass
from pathlib import Path

# アプリデータの保存先 (ログインセッション・DB・キャッシュ)
DATA_DIR = Path.home() / ".allapp"
PROFILES_DIR = DATA_DIR / "profiles"
DB_PATH = DATA_DIR / "allapp.sqlite3"

# 埋め込みブラウザのUser-Agent (QtWebEngineトークンを含むUAだと
# 一部サイトのログインがブロックされるため、Chrome相当のUAを使う)
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class Platform:
    id: str                 # 内部ID (プロファイルのフォルダ名にも使用)
    name: str               # 表示名
    category: str           # プルダウンのグループ名
    home_url: str           # ホーム画面URL
    account_url_format: str # ハンドル名からプロフィールURLを作る書式
    trend_fallback_url: str # 自動取得できない時に開くトレンドページ
    trend_criteria: str     # ネタ収集の基準の説明
    metrics: tuple          # 実績パネルの数値列ラベル (4つ)
    auto_trend: bool = False  # トレンド自動取得に対応しているか
    post_url: str = ""      # 投稿作成画面のURL (空ならhome_urlを使う)
    intent_format: str = ""  # 投稿文を{text}で埋め込めるインテントURL
    post_note: str = ""     # 投稿方法の補足 (公式アプリ推奨など)


# よく使うメトリクスのプリセット
_M_SNS = ("閲覧数", "いいね", "フォロワー増", "収益(円)")
_M_VIDEO = ("再生数", "いいね", "フォロワー増", "収益(円)")
_M_LIVE = ("視聴者数", "ギフト/投げ銭", "フォロワー増", "収益(円)")
_M_SALES = ("閲覧数", "いいね/スキ", "販売数", "売上(円)")
_M_MEMBER = ("閲覧数", "いいね", "支援者数", "支援額(円)")

PLATFORMS: list[Platform] = [
    # ---------------------------------------------------- SNS・テキスト
    Platform(
        id="x", name="X (Twitter)", category="SNS・テキスト",
        home_url="https://x.com/home",
        account_url_format="https://x.com/{handle}",
        trend_fallback_url="https://x.com/explore/tabs/trending",
        trend_criteria="基準: 約10万インプレッション級の急上昇トレンド",
        metrics=("インプレッション", "いいね", "リポスト", "収益(円)"),
        auto_trend=True,
        post_url="https://x.com/compose/post",
        intent_format="https://x.com/intent/post?text={text}",
    ),
    Platform(
        id="threads", name="Threads", category="SNS・テキスト",
        home_url="https://www.threads.net/",
        account_url_format="https://www.threads.net/@{handle}",
        trend_fallback_url="https://www.threads.net/",
        trend_criteria="基準: おすすめフィードの急上昇投稿 (手動確認)",
        metrics=_M_SNS,
        intent_format="https://www.threads.net/intent/post?text={text}",
    ),
    Platform(
        id="instagram", name="Instagram", category="SNS・テキスト",
        home_url="https://www.instagram.com/",
        account_url_format="https://www.instagram.com/{handle}/",
        trend_fallback_url="https://www.instagram.com/explore/",
        trend_criteria="基準: 発見タブの急上昇リール/投稿 (手動確認)",
        metrics=_M_VIDEO,
        post_note="投稿はInstagram公式アプリからが確実です",
    ),
    Platform(
        id="pinterest", name="Pinterest", category="SNS・テキスト",
        home_url="https://www.pinterest.jp/",
        account_url_format="https://www.pinterest.jp/{handle}/",
        trend_fallback_url="https://jp.trends.pinterest.com/",
        trend_criteria="基準: Pinterest Trends の急上昇キーワード",
        metrics=("インプレッション", "保存数", "アウトバウンドクリック", "収益(円)"),
        post_url="https://www.pinterest.com/pin-builder/",
    ),
    Platform(
        id="linevoom", name="LINE VOOM", category="SNS・テキスト",
        home_url="https://voom.line.me/",
        account_url_format="https://voom.line.me/",
        trend_fallback_url="https://voom.line.me/",
        trend_criteria="基準: おすすめフィードの人気動画 (手動確認)",
        metrics=_M_VIDEO,
        post_note="投稿はLINE公式アプリのVOOMタブから",
    ),
    # ------------------------------------------------------------ 動画
    Platform(
        id="youtube", name="YouTube", category="動画",
        home_url="https://www.youtube.com/",
        account_url_format="https://www.youtube.com/@{handle}",
        trend_fallback_url="https://www.youtube.com/",
        trend_criteria="基準: 投稿3日以内かつ10万再生以上を優先 (自動取得)",
        metrics=("再生数", "高評価", "登録者増", "収益(円)"),
        auto_trend=True,
        post_url="https://studio.youtube.com/",
        post_note="アップロードはYouTube Studio (要ログイン) から",
    ),
    Platform(
        id="tiktok", name="TikTok", category="動画",
        home_url="https://www.tiktok.com/",
        account_url_format="https://www.tiktok.com/@{handle}",
        trend_fallback_url=(
            "https://ads.tiktok.com/business/creativecenter/inspiration/"
            "popular/hashtag/pc/ja"
        ),
        trend_criteria="基準: クリエイティブセンターの人気ハッシュタグ",
        metrics=_M_VIDEO,
        post_url="https://www.tiktok.com/tiktokstudio/upload",
        post_note="TikTok公式アプリからの投稿も可",
    ),
    Platform(
        id="niconico", name="ニコニコ動画", category="動画",
        home_url="https://www.nicovideo.jp/",
        account_url_format="https://www.nicovideo.jp/user/{handle}",
        trend_fallback_url="https://www.nicovideo.jp/ranking",
        trend_criteria="基準: 24時間総合ランキング上位3件 (自動取得)",
        metrics=("再生数", "コメント", "マイリスト", "収益(円)"),
        auto_trend=True,
        post_url="https://garage.nicovideo.jp/",
    ),
    Platform(
        id="rumble", name="Rumble (海外)", category="動画",
        home_url="https://rumble.com/",
        account_url_format="https://rumble.com/c/{handle}",
        trend_fallback_url="https://rumble.com/browse",
        trend_criteria="基準: Browseページの人気動画 (手動確認)",
        metrics=_M_VIDEO,
        post_url="https://rumble.com/upload.php",
    ),
    Platform(
        id="dailymotion", name="Dailymotion (海外)", category="動画",
        home_url="https://www.dailymotion.com/jp",
        account_url_format="https://www.dailymotion.com/{handle}",
        trend_fallback_url="https://www.dailymotion.com/jp",
        trend_criteria="基準: トップページの人気動画 (手動確認)",
        metrics=_M_VIDEO,
        post_url="https://www.dailymotion.com/partner",
    ),
    # ------------------------------------------------------ ライブ配信
    Platform(
        id="17live", name="イチナナ (17LIVE)", category="ライブ配信",
        home_url="https://17.live/ja",
        account_url_format="https://17.live/ja/profile/r/{handle}",
        trend_fallback_url="https://17.live/ja",
        trend_criteria="基準: トップページの人気ライバー (手動確認)",
        metrics=_M_LIVE,
        post_note="配信は17LIVE公式アプリから",
    ),
    Platform(
        id="twitch", name="Twitch (海外)", category="ライブ配信",
        home_url="https://www.twitch.tv/",
        account_url_format="https://www.twitch.tv/{handle}",
        trend_fallback_url="https://www.twitch.tv/directory",
        trend_criteria="基準: カテゴリ別視聴者数上位 (手動確認)",
        metrics=_M_LIVE,
        post_url="https://dashboard.twitch.tv/",
        post_note="配信は公式アプリまたはOBSから",
    ),
    Platform(
        id="pococha", name="Pococha", category="ライブ配信",
        home_url="https://www.pococha.com/",
        account_url_format="https://www.pococha.com/",
        trend_fallback_url="https://www.pococha.com/",
        trend_criteria="基準: 人気ライバーランキング (手動確認)",
        metrics=_M_LIVE,
        post_note="配信はPococha公式アプリから",
    ),
    Platform(
        id="showroom", name="SHOWROOM", category="ライブ配信",
        home_url="https://www.showroom-live.com/",
        account_url_format="https://www.showroom-live.com/r/{handle}",
        trend_fallback_url="https://www.showroom-live.com/ranking",
        trend_criteria="基準: ランキングページ上位 (手動確認)",
        metrics=_M_LIVE,
        post_note="配信はSHOWROOM公式アプリから",
    ),
    # ---------------------------------------- コンテンツ販売・ブログ
    Platform(
        id="note", name="note", category="コンテンツ販売・ブログ",
        home_url="https://note.com/",
        account_url_format="https://note.com/{handle}",
        trend_fallback_url="https://note.com/search?context=note&q=&sort=popular",
        trend_criteria="基準: 人気(売れ筋)記事の上位 (手動確認)",
        metrics=("ビュー", "スキ", "販売数", "売上(円)"),
        post_url="https://note.com/notes/new",
    ),
    Platform(
        id="brain", name="Brain", category="コンテンツ販売・ブログ",
        home_url="https://brain-market.com/",
        account_url_format="https://brain-market.com/u/{handle}",
        trend_fallback_url="https://brain-market.com/",
        trend_criteria="基準: 人気ランキング上位 (手動確認)",
        metrics=_M_SALES,
    ),
    Platform(
        id="tips", name="Tips", category="コンテンツ販売・ブログ",
        home_url="https://tips.jp/",
        account_url_format="https://tips.jp/u/{handle}",
        trend_fallback_url="https://tips.jp/",
        trend_criteria="基準: 人気コンテンツ上位 (手動確認)",
        metrics=_M_SALES,
    ),
    Platform(
        id="kdp", name="Kindle出版 (KDP)", category="コンテンツ販売・ブログ",
        home_url="https://kdp.amazon.co.jp/",
        account_url_format="https://kdp.amazon.co.jp/",
        trend_fallback_url="https://www.amazon.co.jp/gp/bestsellers/digital-text",
        trend_criteria="基準: Kindleベストセラーランキング (手動確認)",
        metrics=("既読KENP", "レビュー数", "販売数", "ロイヤリティ(円)"),
        post_note="出版作業はPCのKDP管理画面推奨",
    ),
    Platform(
        id="booth", name="BOOTH", category="コンテンツ販売・ブログ",
        home_url="https://booth.pm/ja",
        account_url_format="https://{handle}.booth.pm/",
        trend_fallback_url="https://booth.pm/ja",
        trend_criteria="基準: 人気商品 (手動確認)",
        metrics=_M_SALES,
        post_url="https://manage.booth.pm/items/new",
    ),
    Platform(
        id="coconala", name="ココナラ", category="コンテンツ販売・ブログ",
        home_url="https://coconala.com/",
        account_url_format="https://coconala.com/users/{handle}",
        trend_fallback_url="https://coconala.com/categories",
        trend_criteria="基準: カテゴリ別人気サービス (手動確認)",
        metrics=("閲覧数", "お気に入り", "販売数", "売上(円)"),
        post_url="https://coconala.com/mypage",
    ),
    Platform(
        id="fc2blog", name="FC2ブログ", category="コンテンツ販売・ブログ",
        home_url="https://blog.fc2.com/",
        account_url_format="https://{handle}.blog.fc2.com/",
        trend_fallback_url="https://blogranking.fc2.com/",
        trend_criteria="基準: FC2ブログランキング上位 (手動確認)",
        metrics=("PV", "拍手", "読者増", "収益(円)"),
        post_url="https://admin.blog.fc2.com/",
    ),
    Platform(
        id="medium", name="Medium (海外)", category="コンテンツ販売・ブログ",
        home_url="https://medium.com/",
        account_url_format="https://medium.com/@{handle}",
        trend_fallback_url="https://medium.com/",
        trend_criteria="基準: トップページのTrending (手動確認)",
        metrics=("ビュー", "拍手(Claps)", "フォロワー増", "収益(円)"),
        post_url="https://medium.com/new-story",
    ),
    Platform(
        id="substack", name="Substack (海外)", category="コンテンツ販売・ブログ",
        home_url="https://substack.com/",
        account_url_format="https://{handle}.substack.com/",
        trend_fallback_url="https://substack.com/browse",
        trend_criteria="基準: カテゴリ別人気ニュースレター (手動確認)",
        metrics=("開封数", "いいね", "購読者増", "収益(円)"),
    ),
    # ------------------------------------ メンバーシップ・ファン支援
    Platform(
        id="fanbox", name="pixivFANBOX", category="メンバーシップ・支援",
        home_url="https://www.fanbox.cc/",
        account_url_format="https://{handle}.fanbox.cc/",
        trend_fallback_url="https://www.fanbox.cc/",
        trend_criteria="基準: トップの注目クリエイター (手動確認)",
        metrics=_M_MEMBER,
        post_url="https://www.fanbox.cc/manage/posts",
    ),
    Platform(
        id="fantia", name="Fantia", category="メンバーシップ・支援",
        home_url="https://fantia.jp/",
        account_url_format="https://fantia.jp/fanclubs/{handle}",
        trend_fallback_url="https://fantia.jp/",
        trend_criteria="基準: 人気ファンクラブランキング (手動確認)",
        metrics=_M_MEMBER,
    ),
    Platform(
        id="cien", name="Ci-en", category="メンバーシップ・支援",
        home_url="https://ci-en.net/",
        account_url_format="https://ci-en.net/creator/{handle}",
        trend_fallback_url="https://ci-en.net/",
        trend_criteria="基準: 注目クリエイター (手動確認)",
        metrics=_M_MEMBER,
    ),
    Platform(
        id="patreon", name="Patreon (海外)", category="メンバーシップ・支援",
        home_url="https://www.patreon.com/",
        account_url_format="https://www.patreon.com/{handle}",
        trend_fallback_url="https://www.patreon.com/explore",
        trend_criteria="基準: Exploreの人気クリエイター (手動確認)",
        metrics=_M_MEMBER,
        post_url="https://www.patreon.com/posts/new",
    ),
    # ------------------------------------------------------------ 音声
    Platform(
        id="standfm", name="stand.fm", category="音声",
        home_url="https://stand.fm/",
        account_url_format="https://stand.fm/channels/{handle}",
        trend_fallback_url="https://stand.fm/",
        trend_criteria="基準: 人気チャンネル (手動確認)",
        metrics=("再生数", "いいね", "フォロワー増", "収益(円)"),
        post_note="収録・配信はstand.fm公式アプリから",
    ),
    Platform(
        id="spoon", name="Spoon", category="音声",
        home_url="https://www.spooncast.net/jp/",
        account_url_format="https://www.spooncast.net/jp/profile/{handle}",
        trend_fallback_url="https://www.spooncast.net/jp/",
        trend_criteria="基準: 人気配信ランキング (手動確認)",
        metrics=_M_LIVE,
        post_note="配信はSpoon公式アプリから",
    ),
]

PLATFORM_BY_ID: dict[str, Platform] = {p.id: p for p in PLATFORMS}

# プルダウンのグループ表示順
PLATFORM_CATEGORIES = [
    "SNS・テキスト", "動画", "ライブ配信",
    "コンテンツ販売・ブログ", "メンバーシップ・支援", "音声",
]


# ---------------------------------------------------------------- ASP
@dataclass(frozen=True)
class Asp:
    id: str
    name: str
    login_url: str   # 管理画面 (ログインページ)
    note: str        # 特徴メモ


ASPS: list[Asp] = [
    Asp("a8", "A8.net", "https://www.a8.net/",
        "国内最大手。案件数No.1、審査なしで登録可"),
    Asp("moshimo", "もしもアフィリエイト", "https://af.moshimo.com/",
        "W報酬制度(+12%)。Amazon/楽天の同時提携に強い"),
    Asp("valuecommerce", "バリューコマース", "https://www.valuecommerce.ne.jp/",
        "Yahoo!ショッピング系に強い。大手案件多め"),
    Asp("afb", "afb (アフィビー)", "https://www.afi-b.com/",
        "美容・健康系に強い。報酬支払いが早い(翌月末)"),
    Asp("accesstrade", "アクセストレード", "https://www.accesstrade.ne.jp/",
        "金融・ゲーム・通信系に強い"),
    Asp("rakuten", "楽天アフィリエイト", "https://affiliate.rakuten.co.jp/",
        "楽天市場の全商品を紹介可能。料率2〜4%"),
    Asp("amazon", "Amazonアソシエイト", "https://affiliate.amazon.co.jp/",
        "Amazon全商品。審査あり(180日以内に3件成約)"),
    Asp("infotop", "インフォトップ", "https://www.infotop.jp/",
        "情報商材系。高単価(報酬50%超も)"),
    Asp("adsense", "Google AdSense", "https://adsense.google.com/",
        "クリック報酬型。ブログ/YouTube収益の定番"),
]

ASP_BY_ID: dict[str, Asp] = {a.id: a for a in ASPS}


# ---------------------------------------------------------- AIサービス
@dataclass(frozen=True)
class AiService:
    id: str
    name: str
    url: str
    category: str  # 文章 / 画像 / 動画 / 音楽


AI_SERVICES: list[AiService] = [
    AiService("claude", "Claude", "https://claude.ai/new", "文章"),
    AiService("chatgpt", "ChatGPT", "https://chatgpt.com/", "文章"),
    AiService("gemini", "Gemini", "https://gemini.google.com/app", "文章"),
    AiService("grok", "Grok", "https://grok.com/", "文章"),
    AiService("copilot", "Microsoft Copilot",
              "https://copilot.microsoft.com/", "文章"),
    AiService("perplexity", "Perplexity",
              "https://www.perplexity.ai/", "文章"),
    AiService("deepseek", "DeepSeek", "https://chat.deepseek.com/", "文章"),
    AiService("midjourney", "Midjourney",
              "https://www.midjourney.com/", "画像"),
    AiService("ideogram", "Ideogram", "https://ideogram.ai/", "画像"),
    AiService("leonardo", "Leonardo.Ai", "https://app.leonardo.ai/", "画像"),
    AiService("bingimage", "Bing Image Creator",
              "https://www.bing.com/images/create", "画像"),
    AiService("sora", "Sora", "https://sora.chatgpt.com/", "動画"),
    AiService("runway", "Runway", "https://app.runwayml.com/", "動画"),
    AiService("pika", "Pika", "https://pika.art/", "動画"),
    AiService("kling", "Kling AI", "https://klingai.com/", "動画"),
    AiService("hailuo", "Hailuo AI", "https://hailuoai.video/", "動画"),
    AiService("suno", "Suno (音楽)", "https://suno.com/", "音楽"),
    AiService("udio", "Udio (音楽)", "https://www.udio.com/", "音楽"),
]

AI_CATEGORIES = ["文章", "画像", "動画", "音楽"]

# 後方互換 (旧コードで参照)
CLAUDE_URL = "https://claude.ai/new"
CHATGPT_URL = "https://chatgpt.com/"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
