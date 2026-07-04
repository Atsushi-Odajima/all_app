"""当たり障りのない自動返信の定型文プールと、返信してよいかの安全判定

設計方針 (レビュー指摘 C-3 反映):
- 返信対象は「自分の自動投稿への直接の返信」のみ。mentions全体には触らない
- 否定的な内容・URL付き・複数メンション巻き込みには自動返信しない
  (炎上相手やスパムに定型文を返すと逆効果のため)
"""
import random
import re

# ============================================================
# ★カスタマイズポイント★
# あなたの「部下」の人柄はこの返信プールで決まります。
# 自由に追加・削除してください (ペルソナの口調に合わせて選ばれます)
# ============================================================
REPLY_POOL: list[str] = [
    "ありがとうございます！",
    "ありがとうございます！励みになります",
    "光栄です！",
    "嬉しいお言葉ありがとうございます",
    "まだまだ勉強不足ですが頑張ります！",
    "そう言っていただけて嬉しいです",
    "コメントありがとうございます！",
    "参考になれば嬉しいです！",
    "これからも頑張ります！",
    "気づきをいただきありがとうございます",
]

# 語尾のゆらぎ (毎回同じ文面だとbotっぽくなるため)
_SUFFIX_POOL = ["", "", "", "🙏", "✨", "😊", "！"]

# この単語を含む返信には自動返信しない (安全側に倒す)
_NEGATIVE_WORDS = [
    "嘘", "デマ", "違う", "間違", "おかしい", "詐欺", "怪しい", "胡散臭",
    "パクリ", "盗用", "通報", "訴え", "消せ", "削除", "死", "殺",
    "きもい", "キモい", "うざい", "ウザい", "ばか", "バカ", "アホ",
    "csam", "spam",
]


def pick_reply(tone: str = "") -> str:
    """定型文プールからランダムに1つ選び、語尾ゆらぎを付ける"""
    base = random.choice(REPLY_POOL)
    suffix = random.choice(_SUFFIX_POOL)
    if suffix and base.endswith(("！", "！", "です", "ます")):
        return base + suffix
    return base


def is_safe_to_reply(their_text: str) -> tuple[bool, str]:
    """この相手に定型文を返して安全かを判定する。(可否, 理由)"""
    text = their_text.strip()
    if not text:
        return False, "本文が空"
    lower = text.lower()
    for w in _NEGATIVE_WORDS:
        if w in lower:
            return False, f"否定的な語を含む ({w})"
    if re.search(r"https?://", lower):
        return False, "URL付き (スパムの可能性)"
    if lower.count("@") >= 2:
        return False, "複数メンションの巻き込み"
    if len(text) > 280:
        return False, "長文 (定型文では不適切)"
    return True, ""
