/* All/App モバイル版 SPA */
"use strict";

const state = {
  init: null,
  platform: null,
  links: [],
};

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- 共通
async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

const post = (path, body) => api(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const patch = (path, body) => api(path, {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const del = (path) => api(path, { method: "DELETE" });

let toastTimer = null;
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 1800);
}

function copyText(text) {
  // http://192.168.x.x は非セキュアコンテキストのため
  // navigator.clipboard が使えない場合は旧方式にフォールバック
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text)
      .then(() => true).catch(() => legacyCopy(text));
  }
  return Promise.resolve(legacyCopy(text));
}
function legacyCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, text.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  document.body.removeChild(ta);
  return ok;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) node.appendChild(c);
  return node;
}

// ---------------------------------------------------------------- 初期化
async function boot() {
  state.init = await api("/api/init");

  // プラットフォーム選択 (カテゴリ別 optgroup)
  const sel = $("platformSelect");
  for (const cat of state.init.categories) {
    const group = el("optgroup", { label: cat });
    for (const p of state.init.platforms) {
      if (p.category === cat) {
        group.appendChild(el("option", { value: p.id, text: p.name }));
      }
    }
    sel.appendChild(group);
  }
  sel.addEventListener("change", () => selectPlatform(sel.value));

  // コンテンツ種類
  for (const t of state.init.content_types) {
    $("contentType").appendChild(el("option", { value: t, text: t }));
  }

  // AIサービス
  for (const cat of state.init.ai_categories) {
    const group = el("optgroup", { label: cat });
    for (const s of state.init.ai_services) {
      if (s.category === cat) {
        group.appendChild(el("option", { value: s.url, text: s.name }));
      }
    }
    $("aiPicker").appendChild(group);
  }

  // ASP
  for (const a of state.init.asps) {
    $("linkAsp").appendChild(el("option", { value: a.name, text: a.name }));
    $("aspList").appendChild(el("div", { class: "card" }, [
      el("div", { class: "title", text: a.name }),
      el("div", { class: "meta", text: a.note }),
      el("a", {
        class: "btn block", href: a.login_url,
        target: "_blank", rel: "noopener", text: "管理画面を開く",
      }),
    ]));
  }

  // 下部タブ
  document.querySelectorAll("nav button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("nav button").forEach(
        (b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".pane").forEach(
        (p) => p.classList.toggle(
          "active", p.id === `pane-${btn.dataset.pane}`));
    });
  });

  bindActions();
  await reloadLinks();
  selectPlatform(state.init.platforms[0].id);
  initAgent();
}

function platformById(id) {
  return state.init.platforms.find((p) => p.id === id);
}

function selectPlatform(id) {
  state.platform = platformById(id);
  $("platformSelect").value = id;
  const p = state.platform;
  $("trendsTitle").textContent = `${p.name} のネタ収集`;
  $("trendsCriteria").textContent = p.trend_criteria;
  $("trendsQuery").classList.toggle("hidden", p.trend_query === "none");
  $("trendsQuery").value = "";
  $("trendsQuery").placeholder =
    p.trend_query === "required"
      ? "キーワード必須 (例: ダイエット、副業、猫)"
      : "検索キーワード (空欄ならトレンド1位を自動使用)";
  $("trendsStatus").textContent =
    p.trend_query === "required"
      ? "キーワードを入れて「更新」を押すと投稿上位5件を表示します"
      : (p.auto_trend || p.trend_query !== "none")
        ? "「更新」で最新のバズ投稿上位5件を取得します"
        : "自動取得未対応です。下のボタンから手動確認してください";
  $("trendsItems").textContent = "";
  $("trendsFallback").href = p.trend_fallback_url;
  $("composeTitle").textContent = `${p.name} 向け記事作成`;
  $("statsTitle").textContent = `${p.name} の実績`;
  $("accountsTitle").textContent = `${p.name} のアカウント`;
  // ログイン・投稿ボタン (アカウントタブ)
  $("loginOpen").href = p.home_url;
  $("postOpen").href = p.post_url;
  $("postNote").textContent = p.post_note || "";
  // 記事作成タブの投稿ノート
  $("goPostNote").textContent = p.intent_format
    ? "投稿文は自動で入力欄にセットされます"
    : (p.post_note || "投稿文をコピーした状態で投稿画面が開きます");
  reloadPosts();
  reloadAccounts();
  reloadDrafts();
}

// ---------------------------------------------------------------- ネタ収集
async function refreshTrends() {
  const p = state.platform;
  $("trendsRefresh").disabled = true;
  $("trendsStatus").textContent = "取得中...";
  try {
    const q = encodeURIComponent($("trendsQuery").value || "");
    const r = await api(`/api/trends/${p.id}?q=${q}`);
    $("trendsStatus").textContent = r.note.split("\n")[0];
    const host = $("trendsItems");
    host.textContent = "";
    r.items.forEach((item, i) => {
      host.appendChild(el("div", { class: "card" }, [
        el("div", { class: "title", text: `${i + 1}位  ${item.title}` }),
        el("div", { class: "meta", text: item.metric }),
        el("div", { class: "row" }, [
          el("a", {
            class: "btn", href: item.url,
            target: "_blank", rel: "noopener", text: "開く",
          }),
          el("button", {
            text: "このネタで作成→",
            onclick: () => {
              $("topic").value = item.title;
              document.querySelector('nav button[data-pane="compose"]').click();
            },
          }),
        ]),
      ]));
    });
  } catch (e) {
    $("trendsStatus").textContent = `取得に失敗しました (${e.message})`;
  } finally {
    $("trendsRefresh").disabled = false;
  }
}

// ---------------------------------------------------------------- 記事作成
async function generatePrompt() {
  const r = await post("/api/prompt", {
    platform_id: state.platform.id,
    content_type: $("contentType").value,
    topic: $("topic").value,
    affiliate: $("affiliate").value,
    notes: $("notes").value,
  });
  $("promptOut").value = r.prompt;
}

async function reloadDrafts() {
  const rows = await api(`/api/drafts/${state.platform.id}`);
  const host = $("draftsList");
  host.textContent = "";
  for (const d of rows) {
    host.appendChild(el("div", { class: "card" }, [
      el("div", { class: "title", text: d.title }),
      el("div", { class: "meta", text: d.created_at }),
      el("div", { class: "row" }, [
        el("button", {
          text: "読込",
          onclick: () => {
            $("promptOut").value = d.body;
            $("topic").value = d.title;
          },
        }),
        el("button", {
          class: "danger", text: "削除",
          onclick: async () => {
            await del(`/api/drafts/item/${d.id}`);
            reloadDrafts();
          },
        }),
      ]),
    ]));
  }
}

async function reloadLinks() {
  state.links = await api("/api/links");
  const picker = $("linkPicker");
  picker.textContent = "";
  picker.appendChild(el("option", { value: "", text: "リンク集…" }));
  for (const l of state.links) {
    picker.appendChild(el("option", {
      value: l.url,
      text: l.asp ? `${l.name} (${l.asp})` : l.name,
    }));
  }
  const host = $("linksList");
  host.textContent = "";
  for (const l of state.links) {
    host.appendChild(el("div", { class: "card" }, [
      el("div", { class: "title", text: l.asp ? `${l.name} (${l.asp})` : l.name }),
      el("div", { class: "meta", text: l.url }),
      el("div", { class: "row" }, [
        el("button", {
          text: "URLをコピー",
          onclick: async () => {
            (await copyText(l.url)) ? toast("コピーしました")
                                    : toast("コピーできませんでした");
          },
        }),
        el("button", {
          class: "danger", text: "削除",
          onclick: async () => {
            await del(`/api/links/${l.id}`);
            reloadLinks();
          },
        }),
      ]),
    ]));
  }
}

// ---------------------------------------------------------------- 実績
async function reloadPosts() {
  const p = state.platform;
  const rows = await api(`/api/posts/${p.id}`);
  const totals = [0, 0, 0, 0];
  const host = $("postsList");
  host.textContent = "";
  for (const row of rows) {
    for (let i = 0; i < 4; i++) totals[i] += row[`metric${i + 1}`] || 0;
    const metricsBox = el("div", { class: "metrics" });
    p.metrics.forEach((label, i) => {
      const input = el("input", {
        type: "number", inputmode: "numeric",
        value: row[`metric${i + 1}`] || 0,
      });
      input.addEventListener("change", async () => {
        await patch(`/api/posts/item/${row.id}`, {
          column: `metric${i + 1}`, value: input.value,
        });
        toast("保存しました");
        updateTotals();
      });
      metricsBox.appendChild(el("label", { text: label }, [input]));
    });
    const children = [
      el("div", { class: "title", text: row.title }),
      el("div", {
        class: "meta",
        text: `${row.account_handle || "-"} / ${row.posted_at}`,
      }),
      metricsBox,
    ];
    const btnRow = el("div", { class: "row" });
    if (row.url) {
      btnRow.appendChild(el("a", {
        class: "btn", href: row.url,
        target: "_blank", rel: "noopener", text: "投稿を開く",
      }));
    }
    btnRow.appendChild(el("button", {
      class: "danger", text: "削除",
      onclick: async () => {
        await del(`/api/posts/item/${row.id}`);
        reloadPosts();
      },
    }));
    children.push(btnRow);
    host.appendChild(el("div", { class: "card" }, children));
  }
  $("statsTotals").textContent =
    `合計 (${rows.length}件) ― ` +
    p.metrics.map((m, i) => `${m}: ${totals[i].toLocaleString()}`).join(" / ");
}

async function updateTotals() {
  const p = state.platform;
  const rows = await api(`/api/posts/${p.id}`);
  const totals = [0, 0, 0, 0];
  for (const row of rows)
    for (let i = 0; i < 4; i++) totals[i] += row[`metric${i + 1}`] || 0;
  $("statsTotals").textContent =
    `合計 (${rows.length}件) ― ` +
    p.metrics.map((m, i) => `${m}: ${totals[i].toLocaleString()}`).join(" / ");
}

// ---------------------------------------------------------------- アカウント
async function reloadAccounts() {
  const p = state.platform;
  const rows = await api(`/api/accounts/${p.id}`);
  const host = $("accountsList");
  host.textContent = "";
  for (const a of rows) {
    host.appendChild(el("div", { class: "card" }, [
      el("div", { class: "title", text: `@${a.handle}` }),
      el("div", { class: "meta", text: a.display_name || "" }),
      el("div", { class: "row" }, [
        el("a", {
          class: "btn",
          href: p.account_url_format.replace("{handle}", a.handle),
          target: "_blank", rel: "noopener", text: "プロフィールを開く",
        }),
        el("button", {
          class: "danger", text: "削除",
          onclick: async () => {
            await del(`/api/accounts/item/${a.id}`);
            reloadAccounts();
          },
        }),
      ]),
    ]));
  }
}

// ---------------------------------------------------------------- ボタン類
function bindActions() {
  $("trendsRefresh").addEventListener("click", refreshTrends);
  $("genPrompt").addEventListener("click", () =>
    generatePrompt().catch((e) => toast(e.message)));
  $("copyPrompt").addEventListener("click", async () => {
    const text = $("promptOut").value.trim();
    if (!text) return toast("先にプロンプトを生成してください");
    (await copyText(text)) ? toast("コピーしました")
                           : toast("コピーできませんでした");
  });
  $("saveDraft").addEventListener("click", async () => {
    const body = $("promptOut").value.trim();
    if (!body) return toast("保存する内容がありません");
    await post(`/api/drafts/${state.platform.id}`, {
      title: $("topic").value, body,
    });
    toast("下書きを保存しました");
    reloadDrafts();
  });
  $("openAi").addEventListener("click", async () => {
    const text = $("promptOut").value.trim();
    if (text) await copyText(text);
    toast(text ? "コピーしてAIを開きます" : "AIを開きます");
    window.open($("aiPicker").value, "_blank", "noopener");
  });
  $("linkPicker").addEventListener("change", () => {
    if ($("linkPicker").value) $("affiliate").value = $("linkPicker").value;
  });
  $("goPost").addEventListener("click", async () => {
    const p = state.platform;
    const text = $("postText").value.trim();
    // X / Threads は投稿文を自動セットできるインテントURLを使う
    if (p.intent_format && text) {
      window.open(
        p.intent_format.replace("{text}", encodeURIComponent(text)),
        "_blank", "noopener");
      return;
    }
    if (text) {
      (await copyText(text)) ? toast("投稿文をコピーしました。貼り付けてください")
                             : toast("コピーに失敗。長押しでコピーしてください");
    }
    window.open(p.post_url, "_blank", "noopener");
  });
  $("addPost").addEventListener("click", async () => {
    const title = $("postTitle").value.trim();
    if (!title) return toast("タイトルを入力してください");
    await post(`/api/posts/${state.platform.id}`, {
      title,
      account_handle: $("postAccount").value,
      url: $("postUrl").value,
    });
    $("postTitle").value = "";
    $("postUrl").value = "";
    toast("記録しました");
    reloadPosts();
  });
  $("addAccount").addEventListener("click", async () => {
    const handle = $("accHandle").value.trim();
    if (!handle) return toast("ハンドルを入力してください");
    await post(`/api/accounts/${state.platform.id}`, {
      handle, display_name: $("accName").value,
    });
    $("accHandle").value = "";
    $("accName").value = "";
    toast("追加しました");
    reloadAccounts();
  });
  $("addLink").addEventListener("click", async () => {
    const name = $("linkName").value.trim();
    const url = $("linkUrl").value.trim();
    if (!name || !url) return toast("案件名とURLを入力してください");
    await post("/api/links", { name, url, asp: $("linkAsp").value });
    $("linkName").value = "";
    $("linkUrl").value = "";
    toast("登録しました");
    reloadLinks();
  });
}

// ---------------------------------------------------------------- AI部下
const AGENT_KIND_LABEL = {
  post: "投稿",
  reply_check: "返信チェック",
  buzz_check: "バズチェック",
  send_reply: "返信送信",
  login: "ログイン準備",
};
const AGENT_STATUS_LABEL = {
  pending: "待機",
  running: "実行中",
  done: "完了",
  error: "失敗",
  skipped: "スキップ",
};

function initAgent() {
  $("apAdd").addEventListener("click", () =>
    addAgentPersona().catch((e) => toast(e.message)));
  $("agentSaveKey").addEventListener("click", () =>
    saveAgentKey().catch((e) => toast(e.message)));
  $("agentModalYes").addEventListener("click", () =>
    startAgentDay().catch((e) => toast(e.message)));
  $("agentModalNo").addEventListener("click", () => {
    $("agentModal").classList.add("hidden");
  });

  refreshAgent();
  checkAgentMorningModal();

  setInterval(() => {
    const active = $("pane-agent").classList.contains("active");
    if (document.visibilityState === "visible" && active) {
      refreshAgentStatus();
      refreshAgentLogs();
      refreshAgentReplies();
    }
  }, 10000);
}

async function checkAgentMorningModal() {
  const status = await api("/api/agent/status");
  const personas = await api("/api/agent/personas");
  if (!status.has_plan && personas.length > 0) {
    $("agentModalNote").textContent = status.worker_online
      ? "※PCの電源が入っている時間帯のみ自動投稿されます"
      : "⚠ PCのワーカー(run_agent.bat)が起動していません。プランだけ作成し、ワーカー起動後に実行されます";
    $("agentModal").classList.remove("hidden");
  }
}

async function startAgentDay() {
  try {
    const r = await post("/api/agent/start_day", {});
    if (r.error) {
      toast(r.error);
      return;
    }
    toast(`プラン作成: 投稿${r.posts}件`);
    $("agentModal").classList.add("hidden");
    document.querySelector('nav button[data-pane="agent"]').click();
    refreshAgent();
  } catch (e) {
    toast(e.message);
  }
}

function refreshAgent() {
  refreshAgentStatus();
  refreshAgentPersonas();
  refreshAgentReplies();
  refreshAgentLogs();
  refreshAgentSettings();
}

async function refreshAgentStatus() {
  const status = await api("/api/agent/status");

  const workerHost = $("agentWorkerStatus");
  workerHost.textContent = "";
  workerHost.appendChild(el("div", { class: "card" }, [
    el("div", {}, [
      el("span", { class: status.worker_online ? "dot-ok" : "dot-ng" }),
      el("span", {
        text: status.worker_online
          ? "PC稼働中 — 自動投稿は有効です"
          : "PCオフライン — PCで run_agent.bat を起動するまで自動投稿されません",
      }),
    ]),
  ]));

  const todayHost = $("agentTodayCard");
  todayHost.textContent = "";
  if (!status.has_plan) {
    todayHost.appendChild(el("div", { class: "card" }, [
      el("div", { text: "本日のプランは未作成です" }),
      el("button", {
        class: "primary",
        text: "本日の投稿作業を開始する",
        onclick: () => {
          $("agentModalNote").textContent = status.worker_online
            ? "※PCの電源が入っている時間帯のみ自動投稿されます"
            : "⚠ PCのワーカー(run_agent.bat)が起動していません。プランだけ作成し、ワーカー起動後に実行されます";
          $("agentModal").classList.remove("hidden");
        },
      }),
    ]));
  } else {
    const jobLines = status.jobs.map((job) => {
      const time = (job.run_at || "").slice(11, 16);
      const kindLabel = AGENT_KIND_LABEL[job.kind] || job.kind;
      const statusLabel = AGENT_STATUS_LABEL[job.status] || job.status;
      return el("div", { class: "job-line" }, [
        el("span", { text: `${time} ${kindLabel} @${job.handle}` }),
        el("span", { class: `job-${job.status}`, text: statusLabel }),
      ]);
    });
    todayHost.appendChild(el("div", { class: "card" }, [
      ...jobLines,
      el("button", {
        class: "danger",
        text: "本日の残りを停止",
        onclick: async () => {
          const r = await post("/api/agent/stop", {});
          toast(r.error || `${r.cancelled}件を停止しました`);
          refreshAgentStatus();
        },
      }),
    ]));
  }

  const badge = $("agentReplyBadge");
  badge.textContent = "";
  if (status.pending_replies > 0) {
    badge.appendChild(el("span", { class: "badge", text: String(status.pending_replies) }));
  }
}

async function refreshAgentPersonas() {
  const rows = await api("/api/agent/personas");
  const host = $("agentPersonas");
  host.textContent = "";
  for (const p of rows) {
    const replyState = p.auto_reply
      ? (p.reply_mode === "auto" ? "全自動" : "承認制")
      : "OFF";
    const children = [
      el("div", { class: "title", text: `@${p.handle} (${p.enabled ? "稼働中" : "停止中"})` }),
      el("div", {
        class: "meta",
        text: `テーマ: ${p.theme} / ${p.posts_per_day}回/日 ${p.window_start}-${p.window_end}時 / 返信${replyState}`,
      }),
    ];
    if (p.fail_streak >= 3) {
      children.push(el("div", {
        class: "meta",
        style: "color:#c0392b",
        text: "⚠ 連続失敗により自動停止しました。ログイン準備をやり直して再開してください",
      }));
    }
    children.push(el("div", { class: "row" }, [
      el("button", {
        text: "ログイン準備",
        onclick: async () => {
          const r = await post(`/api/agent/personas/${p.id}/login`, {});
          toast(r.message || r.error);
        },
      }),
      el("button", {
        text: p.enabled ? "停止" : "稼働",
        onclick: async () => {
          await patch(`/api/agent/personas/${p.id}`, { enabled: p.enabled ? 0 : 1 });
          refreshAgentPersonas();
        },
      }),
      el("button", {
        class: "danger",
        text: "削除",
        onclick: async () => {
          if (!confirm(`@${p.handle} を削除しますか？`)) return;
          await del(`/api/agent/personas/${p.id}`);
          refreshAgentPersonas();
        },
      }),
    ]));
    host.appendChild(el("div", { class: "card" }, children));
  }
}

async function refreshAgentReplies() {
  const rows = await api("/api/agent/replies");
  const host = $("agentReplies");
  host.textContent = "";
  if (rows.length === 0) {
    host.appendChild(el("p", { class: "subtle", text: "承認待ちの返信はありません" }));
    return;
  }
  for (const r of rows) {
    const input = el("input", { value: r.our_reply || "" });
    host.appendChild(el("div", { class: "card" }, [
      el("div", { class: "title", text: `@${r.author} さんから (@${r.handle}宛)` }),
      el("div", { class: "meta", text: r.their_text }),
      input,
      el("div", { class: "row" }, [
        el("button", {
          class: "primary",
          text: "この内容で返信",
          onclick: async () => {
            await post(`/api/agent/replies/${r.id}/approve`, { our_reply: input.value });
            toast("返信を予約しました");
            refreshAgentReplies();
          },
        }),
        el("button", {
          text: "返信しない",
          onclick: async () => {
            await post(`/api/agent/replies/${r.id}/reject`, {});
            refreshAgentReplies();
          },
        }),
      ]),
    ]));
  }
}

async function refreshAgentLogs() {
  const rows = await api("/api/agent/logs");
  const host = $("agentLogs");
  host.textContent = "";
  for (const log of rows) {
    const cls = log.level === "warn" ? "log-warn"
      : log.level === "error" ? "log-error"
      : log.level === "ok" ? "log-ok" : "";
    host.appendChild(el("div", {
      class: cls ? `log-line ${cls}` : "log-line",
      text: `${log.at.slice(5, 16)} ${log.message}`,
    }));
  }
}

async function refreshAgentSettings() {
  const s = await api("/api/agent/settings");
  if (s.gemini_api_key_set) {
    $("agentGeminiKey").placeholder = `設定済み (末尾: ${s.gemini_api_key_tail}) — 変更する場合のみ入力`;
  }
}

async function addAgentPersona() {
  const handle = $("apHandle").value.trim();
  const theme = $("apTheme").value.trim();
  if (!handle || !theme) return toast("ハンドルとテーマを入力してください");
  const [windowStart, windowEnd] = $("apWindow").value.split("-");
  await post("/api/agent/personas", {
    platform: "x",
    handle,
    theme,
    tone: $("apTone").value.trim(),
    posts_per_day: Number($("apCount").value),
    window_start: windowStart,
    window_end: windowEnd,
    auto_reply: $("apAutoReply").checked,
    reply_mode: $("apReplyMode").value,
    buzz_threshold: $("apBuzz").value,
    cross_targets: $("apCross").value.trim(),
    hashtags: $("apTags").value.trim(),
  });
  $("apHandle").value = "";
  $("apTheme").value = "";
  $("apTone").value = "";
  $("apBuzz").value = "";
  $("apCross").value = "";
  $("apTags").value = "";
  toast("追加しました。ログイン準備を実行してください");
  refreshAgentPersonas();
}

async function saveAgentKey() {
  const key = $("agentGeminiKey").value.trim();
  if (!key) return toast("キーを入力してください");
  await post("/api/agent/settings", { gemini_api_key: key });
  toast("保存しました");
  $("agentGeminiKey").value = "";
  refreshAgentSettings();
}

boot().catch((e) => toast(`初期化エラー: ${e.message}`));
