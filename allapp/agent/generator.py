"""投稿文の自動生成 — Gemini(無料枠) → Pollinations(無料) → テンプレ の3段構え

ReMaking (manga-studio) と同じフォールバック思想。
どの段で生成されたかはログに残し、全滅しても必ず何か返す。
"""
import json
import random
import re
import urllib.parse

import requests

from ..prompts import PLATFORM_RULES
from . import store

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
POLLINATIONS_URL = "https://text.pollinations.ai/"

# X の日本語投稿は全角140字が上限
X_MAX_LEN = 140


# ---------------------------------------------------------------- LLM呼び出し
def _call_gemini(prompt: str) -> str | None:
    key = store.get_setting("gemini_api_key").strip()
    if not key:
        return None
    try:
        res = requests.post(
            GEMINI_URL,
            params={"key": key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.9,
                                     "maxOutputTokens": 400},
            },
            timeout=45,
        )
        res.raise_for_status()
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        # APIキーがURLに含まれるため、例外メッセージはそのままログに出さない
        store.log("warn", f"Gemini生成に失敗 ({type(e).__name__})。"
                          "Pollinationsに切り替えます")
        return None


def _call_pollinations(prompt: str) -> str | None:
    try:
        res = requests.get(
            POLLINATIONS_URL + urllib.parse.quote(prompt[:2000]),
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        res.raise_for_status()
        text = res.text.strip()
        return text or None
    except Exception as e:
        store.log("warn", f"Pollinations生成に失敗 ({type(e).__name__})。"
                          "テンプレ生成に切り替えます")
        return None


def _call_llm(prompt: str) -> tuple[str | None, str]:
    """(生成文, エンジン名) を返す。全滅なら (None, 'none')"""
    text = _call_gemini(prompt)
    if text:
        return text, "Gemini"
    text = _call_pollinations(prompt)
    if text:
        return text, "Pollinations"
    return None, "none"


# ---------------------------------------------------------------- 整形
def _clean_output(text: str) -> str:
    """LLMの出力から本文だけを取り出す"""
    text = text.strip()
    # コードフェンス除去
    text = re.sub(r"^```[a-z]*\n?|```$", "", text, flags=re.M).strip()
    # 「A案:」「投稿文:」等のラベル行除去
    text = re.sub(r"^(A案|B案|案\d|投稿文|本文)\s*[:：]?\s*\n?", "",
                  text).strip()
    # 前後の引用符除去
    text = text.strip("「」\"'『』")
    return text.strip()


def _truncate_for_x(text: str, hashtags: str) -> str:
    """ハッシュタグ込みで140字に収める"""
    tags = hashtags.strip()
    budget = X_MAX_LEN - (len(tags) + 1 if tags else 0)
    if len(text) > budget:
        text = text[:budget - 1].rstrip() + "…"
    return f"{text}\n{tags}" if tags else text


# ---------------------------------------------------------------- ネタ取得
def _fetch_topic(theme: str) -> str:
    """既存trends.pyでテーマ関連のバズ投稿を1件取ってネタにする"""
    try:
        from ..trends import fetch_trends
        keyword = theme.split("×")[0].split("、")[0].split(" ")[0][:20]
        result = fetch_trends("x", keyword)
        if result.ok and result.items:
            item = random.choice(result.items[:3])
            return item.title[:80]
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------- 投稿生成
_TEMPLATE_PATTERNS = [
    "{theme}について今日も一歩前進。小さな積み重ねが一番の近道だと実感しています。",
    "{theme}を続けていて気づいたこと: 完璧を目指すより、まず続けること。",
    "今日の{theme}メモ。昨日の自分よりちょっとだけ成長できたらそれで十分。",
    "{theme}、始める前は難しく考えすぎていました。やってみると意外とシンプル。",
    "{theme}で大事なのは情報収集より実践。今日も小さく試していきます。",
]


def generate_post(persona: dict) -> tuple[str, str]:
    """ペルソナのテーマに沿った投稿文を生成する。(本文, エンジン名) を返す"""
    theme = persona["theme"]
    tone = persona.get("tone") or "親しみやすい"
    hashtags = (persona.get("hashtags") or "").strip()
    recent = store.recent_agent_posts(persona["id"], limit=5)
    recent_block = ""
    if recent:
        titles = "\n".join(f"- {p['text'][:50]}" for p in recent)
        recent_block = (
            f"\n## 直近の投稿 (これらと内容・書き出しを被らせない)\n{titles}\n")
    topic = _fetch_topic(theme)
    topic_block = f"\n## 今バズっている関連ネタ (使えそうなら絡めてよい)\n{topic}\n" \
        if topic else ""

    rules = PLATFORM_RULES.get(persona["platform"], "")
    prompt = f"""あなたはSNS運用者本人としてX(Twitter)に投稿する日本語の文章を書きます。

## あなたのキャラクター
- テーマ: {theme}
- 口調: {tone}
- 実在の個人として自然に。宣伝臭・AI臭を出さない

## ルール
{rules}
- 全角130字以内、1案のみ
- 本文だけを出力する (ラベル・説明・引用符・ハッシュタグは書かない)
- 絵文字は0〜2個
{recent_block}{topic_block}"""

    text, engine = _call_llm(prompt)
    if text:
        text = _clean_output(text)
        # 複数案が返ってきた場合は最初の段落だけ使う
        text = text.split("\n\n")[0].strip()
    if not text:
        pattern = random.choice(_TEMPLATE_PATTERNS)
        text = pattern.format(theme=theme)
        engine = "テンプレ"
    return _truncate_for_x(text, hashtags), engine


# ---------------------------------------------------------------- 横展開
def rewrite_for_platform(text: str, target_platform_id: str,
                         target_platform_name: str, theme: str) -> str:
    """バズった投稿を別プラットフォーム向けにリライトする"""
    rules = PLATFORM_RULES.get(target_platform_id, "")
    prompt = f"""以下のX(Twitter)でバズった投稿を、{target_platform_name}向けに書き直してください。

## 元の投稿
{text}

## テーマ
{theme}

## {target_platform_name}のルール
{rules}

## 出力
- そのまま投稿できる完成形の本文だけを出力 (説明・ラベル不要)
- 元の投稿の「何がウケたか」を残しつつ、プラットフォームの文化に合わせる"""
    rewritten, _engine = _call_llm(prompt)
    if rewritten:
        return _clean_output(rewritten)
    return text  # 全滅時は原文のまま下書きにする
