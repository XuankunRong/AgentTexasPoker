const els = {
  statusText: document.getElementById("statusText"),
  runSelect: document.getElementById("runSelect"),
  refreshRunsBtn: document.getElementById("refreshRunsBtn"),
  handMeta: document.getElementById("handMeta"),
  blindMeta: document.getElementById("blindMeta"),
  streetMeta: document.getElementById("streetMeta"),
  potMeta: document.getElementById("potMeta"),
  boardCards: document.getElementById("boardCards"),
  seatsGrid: document.getElementById("seatsGrid"),
  metricsMeta: document.getElementById("metricsMeta"),
  metricsTable: document.getElementById("metricsTable"),
  retryMeta: document.getElementById("retryMeta"),
  retryTable: document.getElementById("retryTable"),
  actionFeed: document.getElementById("actionFeed"),
  handsList: document.getElementById("handsList"),
};

const state = {
  runId: null,
  runDir: null,
  lastSeq: 0,
  handId: null,
  street: "-",
  pot: 0,
  dealer: null,
  blinds: null,
  board: [],
  players: {},
  playerOrder: [],
  allPlayerOrder: [],
  positions: {},
  metrics: {},
  metricsHandId: null,
  retrySummary: {},
  actions: [],
  hands: [],
  handSummaries: {},
  handSummariesSnapshot: [],
  handContext: {},
  seenEventSeqs: {},
  seenActionKeys: {},
};

const chartPalette = ["#000000", "#f7b56b", "#bebadc", "#84b2d2", "#ee8075", "#94d1c6"];

const namedPlayerColors = [
  { match: "gpt", color: "#343434" },
  { match: "claude", color: "#f7b56b" },
  { match: "qwen", color: "#bebadc" },
  { match: "gemini", color: "#84b2d2" },
  { match: "minimax", color: "#ee8075" },
  { match: "llama", color: "#94d1c6" },
];

function stableStringify(value) {
  return JSON.stringify(value || {});
}

function formatPercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return "-";
  }
  return `${(num * 100).toFixed(1)}%`;
}

function resetState(keepRun = true) {
  const runId = keepRun ? state.runId : null;
  const runDir = keepRun ? state.runDir : null;
  Object.assign(state, {
    runId,
    runDir,
    lastSeq: 0,
    handId: null,
    street: "-",
    pot: 0,
    dealer: null,
    blinds: null,
    board: [],
    players: {},
    playerOrder: [],
    allPlayerOrder: [],
    positions: {},
    metrics: {},
    metricsHandId: null,
    retrySummary: {},
    actions: [],
    hands: [],
    handSummaries: {},
    handSummariesSnapshot: [],
    handContext: {},
    seenEventSeqs: {},
    seenActionKeys: {},
  });
  render();
}

function playerColor(name, idx) {
  if (name) {
    const lowered = String(name).toLowerCase();
    for (const item of namedPlayerColors) {
      if (lowered.includes(item.match)) {
        return item.color;
      }
    }
  }
  const order = state.allPlayerOrder.length ? state.allPlayerOrder : Object.keys(state.stackSeries);
  const orderIdx = name ? order.indexOf(name) : -1;
  if (orderIdx >= 0) {
    return chartPalette[orderIdx % chartPalette.length];
  }
  if (typeof idx === "number" && idx >= 0) {
    return chartPalette[idx % chartPalette.length];
  }
  return chartPalette[0];
}

function rememberPlayers(names) {
  for (const name of names || []) {
    if (!name) {
      continue;
    }
    if (!state.allPlayerOrder.includes(name)) {
      state.allPlayerOrder.push(name);
    }
  }
}

function addActionItem(title, meta, prompt, response, key = null) {
  const actionKey =
    key || `${title}||${meta || ""}||${prompt || ""}||${response || ""}`;
  if (state.seenActionKeys[actionKey]) {
    return;
  }
  state.seenActionKeys[actionKey] = true;
  state.actions.push({
    ts: new Date().toLocaleTimeString(),
    title,
    meta,
    prompt,
    response,
  });
  if (state.actions.length > 300) {
    state.actions.shift();
  }
}

function processEvent(event) {
  const seq = Number(event.seq || 0);
  if (seq > 0) {
    if (state.seenEventSeqs[seq]) {
      return;
    }
    state.seenEventSeqs[seq] = true;
  }
  if (event.hand_id != null) {
    state.handId = event.hand_id;
  }
  const type = event.type;
  if (type === "hand_start") {
    state.dealer = event.dealer;
    state.blinds = {
      sb: event.small_blind,
      bb: event.big_blind,
    };
    state.street = "preflop";
    state.board = [];
    state.pot = event.pot_before_blinds || 0;
    state.positions = event.positions_by_player || {};
    state.playerOrder = event.table_order_from_dealer || event.participants || [];
    rememberPlayers(state.playerOrder);
    state.handContext[event.hand_id] = {
      dealer: event.dealer,
      blinds: {
        sb: event.small_blind,
        bb: event.big_blind,
      },
      positions: event.positions_by_player || {},
      tableOrder: [...state.playerOrder],
    };
    state.players = {};
    const stacks = event.stacks_before_hand || {};
    const holes = event.hole_cards || {};
    for (const name of state.playerOrder) {
      state.players[name] = {
        stack: stacks[name] ?? null,
        holeCards: holes[name] || [],
        lastAction: "-",
      };
    }
    addActionItem(
      `Hand ${String(state.handId).padStart(4, "0")} start`,
      `Dealer: ${event.dealer} | Blinds: ${event.small_blind?.amount}/${event.big_blind?.amount}`,
      null,
      null,
      `seq:${seq}:hand_start`
    );
    return;
  }

  if (type === "blind_post") {
    const player = event.player;
    const amount = Number(event.amount || 0);
    if (state.players[player] && typeof state.players[player].stack === "number") {
      state.players[player].stack -= amount;
      state.players[player].lastAction = `${event.blind} ${amount}`;
    }
    state.pot = event.pot_after ?? state.pot;
    addActionItem(
      `${player} posted ${event.blind}`,
      `position=${event.player_position || "-"} amount=${amount} pot=${state.pot}`,
      null,
      null,
      `seq:${seq}:blind_post`
    );
    return;
  }

  if (type === "street_start") {
    state.street = event.street || state.street;
    state.board = event.board || [];
    state.pot = event.pot ?? state.pot;
    addActionItem(
      `Street ${state.street}`,
      `board=${state.board.join(" ") || "-"} pot=${state.pot}`,
      null,
      null,
      `seq:${seq}:street_start`
    );
    return;
  }

  if (type === "action") {
    const player = event.player;
    if (!state.players[player]) {
      state.players[player] = { stack: null, holeCards: [], lastAction: "-" };
    }
    state.players[player].stack = event.stack_after;
    const amountPart =
      event.final_action === "call" || event.final_action === "raise"
        ? ` ${event.final_amount}`
        : "";
    state.players[player].lastAction = `${event.final_action}${amountPart}`;
    state.pot = event.pot_after ?? state.pot;
    const dialogue = event.agent_dialogue || {};
    addActionItem(
      `${player} (${event.player_position || "-"}) -> ${event.final_action}${amountPart}`,
      `street=${event.street} to_call=${event.to_call} pot=${event.pot_before}->${event.pot_after}`,
      dialogue.prompt || null,
      dialogue.raw_response || dialogue.error || null,
      `seq:${seq}:action`
    );
    return;
  }

  if (type === "hand_end") {
    state.board = event.community_cards || state.board;
    state.pot = event.result?.pot ?? state.pot;
    const stacks = event.stacks || {};
    rememberPlayers(Object.keys(stacks));
    for (const [name, val] of Object.entries(stacks)) {
      if (!state.players[name]) {
        state.players[name] = { stack: null, holeCards: [], lastAction: "-" };
      }
      state.players[name].stack = val;
    }
    const winners = (event.result?.winners || []).join(", ");
    const winnerList = event.result?.winners || [];
    const potValue = Number(event.result?.pot || 0);
    const handId = event.hand_id ?? state.handId ?? 0;
    const handCtx = state.handContext[handId] || {};
    const showdown = event.result?.showdown ? "showdown" : "no-showdown";
    state.handSummaries[handId] = {
      handId,
      dealer: handCtx.dealer || state.dealer,
      winners,
      pot: state.pot,
      showdown,
      street: state.street,
      board: [...state.board],
    };
    addActionItem(
      `Hand ${String(state.handId).padStart(4, "0")} end`,
      `winners=${winners} pot=${state.pot} ${showdown}`,
      null,
      null,
      `seq:${seq}:hand_end`
    );
    return;
  }

  if (type === "risk_metrics_update") {
    state.metrics = event.metrics || {};
    state.metricsHandId = event.hand_id || state.metricsHandId;
    return;
  }

  if (type === "hand_reflection") {
    addActionItem(
      `Reflection ${event.player}`,
      `net=${event.net_chip_change} think=${event.thinking_time_sec}s`,
      null,
      event.self_assessment || null,
      `seq:${seq}:hand_reflection`
    );
  }
}

function renderMetrics() {
  const handLabel =
    state.metricsHandId == null ? "尚无指标" : `统计截至 Hand ${String(state.metricsHandId).padStart(4, "0")}`;
  els.metricsMeta.textContent = handLabel;
  els.metricsTable.innerHTML = "";

  const header = document.createElement("div");
  header.className = "metrics-row header";
  header.innerHTML = `
    <div>Player</div>
    <div>Hands</div>
    <div>Entered</div>
    <div>Play Rate</div>
    <div>Raise Rate</div>
    <div>Aggression</div>
  `;
  els.metricsTable.appendChild(header);

  const players = Object.entries(state.metrics || {});
  for (const [name, row] of players) {
    const block = document.createElement("div");
    block.className = "metrics-row";
    block.innerHTML = `
      <div class="metrics-player">${name}</div>
      <div>${row.hands_played ?? "-"}</div>
      <div>${row.entered_hands ?? row.vpip_hands ?? "-"}</div>
      <div>${row.vpip ?? "-"}</div>
      <div>${row.pfr ?? "-"}</div>
      <div>${row.aggression_factor_raw ?? "-"}</div>
    `;
    els.metricsTable.appendChild(block);
  }
}

function renderRetrySummary() {
  const players = Object.entries(state.retrySummary || {});
  els.retryMeta.textContent =
    players.length === 0 ? "尚无重试统计" : `失败原因按 retry 尝试统计，共 ${players.length} 位玩家`;
  els.retryTable.innerHTML = "";

  const header = document.createElement("div");
  header.className = "metrics-row retry-row header";
  header.innerHTML = `
    <div>Player</div>
    <div>Decisions</div>
    <div>Retried</div>
    <div>Recovered</div>
    <div>Exhausted</div>
    <div>Main Issue</div>
    <div>Breakdown</div>
  `;
  els.retryTable.appendChild(header);

  for (const [name, row] of players) {
    const block = document.createElement("div");
    block.className = "metrics-row retry-row";
    block.innerHTML = `
      <div class="metrics-player">${name}</div>
      <div>${row.decisions ?? "-"}</div>
      <div>${row.decisions_with_retry ?? "-"}</div>
      <div>${row.succeeded_after_retry ?? "-"}</div>
      <div>${row.exhausted_after_retry ?? "-"}</div>
      <div>${row.top_issue_label || "-"}</div>
      <div>${row.issue_summary || "-"}</div>
    `;
    els.retryTable.appendChild(block);
  }
}

function renderMeta() {
  els.handMeta.textContent =
    state.handId == null ? "Hand: -" : `Hand: ${String(state.handId).padStart(4, "0")}`;
  if (state.blinds) {
    els.blindMeta.textContent = `Blinds: SB ${state.blinds.sb?.player} ${state.blinds.sb?.amount} | BB ${state.blinds.bb?.player} ${state.blinds.bb?.amount}`;
  } else {
    els.blindMeta.textContent = "Blinds: -";
  }
  els.streetMeta.textContent = `Street: ${state.street || "-"}`;
  els.potMeta.textContent = `Pot: ${state.pot ?? "-"}`;
}

function renderBoard() {
  els.boardCards.innerHTML = "";
  if (!state.board.length) {
    const empty = document.createElement("span");
    empty.className = "card-chip";
    empty.textContent = "-";
    els.boardCards.appendChild(empty);
    return;
  }
  for (const c of state.board) {
    const el = document.createElement("span");
    el.className = "card-chip";
    el.textContent = c;
    els.boardCards.appendChild(el);
  }
}

function renderSeats() {
  els.seatsGrid.innerHTML = "";
  const order = state.playerOrder.length ? state.playerOrder : Object.keys(state.players);
  for (const name of order) {
    const p = state.players[name] || { stack: "-", holeCards: [], lastAction: "-" };
    const card = document.createElement("div");
    card.className = "seat-card";
    card.innerHTML = `
      <div class="seat-head">
        <span class="seat-name">${name}</span>
        <span class="seat-pos">${state.positions[name] || "-"}</span>
      </div>
      <div class="seat-stack">Stack: ${p.stack ?? "-"}</div>
      <div class="seat-hole">Hole: ${(p.holeCards || []).join(" ") || "-"}</div>
      <div class="seat-action">Last: ${p.lastAction || "-"}</div>
    `;
    els.seatsGrid.appendChild(card);
  }
}

function renderActionFeed() {
  els.actionFeed.innerHTML = "";
  for (const item of [...state.actions].reverse()) {
    const block = document.createElement("div");
    block.className = "action-item";
    const promptHtml = item.prompt
      ? `<details><summary>Prompt</summary><pre>${item.prompt.replace(/</g, "&lt;")}</pre></details>`
      : "";
    const responseHtml = item.response
      ? `<details><summary>Response</summary><pre>${item.response.replace(/</g, "&lt;")}</pre></details>`
      : "";
    block.innerHTML = `
      <div class="action-title">${item.title}</div>
      <div class="action-meta">${item.meta || ""} | ${item.ts}</div>
      ${promptHtml}
      ${responseHtml}
    `;
    els.actionFeed.appendChild(block);
  }
}

function renderHands() {
  els.handsList.innerHTML = "";
  const hands =
    state.handSummariesSnapshot.length > 0
      ? state.handSummariesSnapshot.slice(0, 120)
      : Object.values(state.handSummaries || {})
          .sort((a, b) => Number(b.handId || 0) - Number(a.handId || 0))
          .slice(0, 120);
  for (const hand of hands) {
    const handCtx = state.handContext[hand.handId] || {};
    const block = document.createElement("div");
    block.className = "hand-item";
    block.innerHTML = `
      <div><strong>Hand ${String(hand.handId).padStart(4, "0")}</strong></div>
      <div>Dealer: ${handCtx.dealer || hand.dealer || "-"}</div>
      <div>Winners: ${hand.winners || "-"}</div>
      <div>Pot: ${hand.pot}</div>
      <div>Board: ${(hand.board || []).join(" ") || "-"}</div>
      <div>Result: ${hand.showdown}</div>
    `;
    els.handsList.appendChild(block);
  }
}

function render() {
  renderMeta();
  renderBoard();
  renderSeats();
  renderMetrics();
  renderRetrySummary();
  renderActionFeed();
  renderHands();
}

async function loadRuns() {
  try {
    const rsp = await fetch("/api/runs");
    const data = await rsp.json();
    const runs = data.runs || [];
    if (!runs.length) {
      els.statusText.textContent = "未发现 run 日志目录";
      return;
    }

    const previous = state.runId;
    els.runSelect.innerHTML = "";
    for (const run of runs) {
      const opt = document.createElement("option");
      opt.value = run.id;
      opt.textContent = run.id;
      els.runSelect.appendChild(opt);
    }
    if (previous && runs.some((r) => r.id === previous)) {
      els.runSelect.value = previous;
      state.runId = previous;
    } else {
      state.runId = runs[0].id;
      els.runSelect.value = state.runId;
      resetState(true);
    }
  } catch (err) {
    els.statusText.textContent = `加载 runs 失败: ${String(err)}`;
  }
}

async function pollEvents() {
  if (!state.runId) {
    return;
  }
  try {
    const url = `/api/events?since=${state.lastSeq}&run=${encodeURIComponent(state.runId)}`;
    const rsp = await fetch(url);
    if (!rsp.ok) {
      els.statusText.textContent = `读取事件失败: HTTP ${rsp.status}`;
      return;
    }
    const data = await rsp.json();
    state.runDir = data.run_dir;
    const events = data.events || [];
    let shouldRender = events.length > 0;
    for (const event of events) {
      processEvent(event);
    }
    const snapshotMetrics = data.risk_metrics || {};
    const snapshotRetrySummary = data.retry_summary || {};
    const snapshotHandSummaries = data.hand_summaries || [];
    if (Object.keys(snapshotMetrics).length > 0) {
      const latestMetricsEvent = data.latest_risk_metrics_event || null;
      const nextMetricsSig = stableStringify(snapshotMetrics);
      const currentMetricsSig = stableStringify(state.metrics);
      const nextHandId =
        latestMetricsEvent && latestMetricsEvent.hand_id != null
          ? latestMetricsEvent.hand_id
          : state.metricsHandId;
      if (nextMetricsSig !== currentMetricsSig || nextHandId !== state.metricsHandId) {
        state.metrics = snapshotMetrics;
        state.metricsHandId = nextHandId;
        shouldRender = true;
      }
    }
    const nextRetrySig = stableStringify(snapshotRetrySummary);
    const currentRetrySig = stableStringify(state.retrySummary);
    if (nextRetrySig !== currentRetrySig) {
      state.retrySummary = snapshotRetrySummary;
      shouldRender = true;
    }
    const nextHandsSig = stableStringify(snapshotHandSummaries);
    const currentHandsSig = stableStringify(state.handSummariesSnapshot);
    if (nextHandsSig !== currentHandsSig) {
      state.handSummariesSnapshot = snapshotHandSummaries;
      shouldRender = true;
    }
    state.lastSeq = data.max_seq || state.lastSeq;
    els.statusText.textContent = `run=${state.runId} | seq=${state.lastSeq} | ${new Date().toLocaleTimeString()}`;
    if (shouldRender) {
      render();
    }
  } catch (err) {
    els.statusText.textContent = `轮询失败: ${String(err)}`;
  }
}

els.refreshRunsBtn.addEventListener("click", async () => {
  await loadRuns();
  render();
});

els.runSelect.addEventListener("change", () => {
  state.runId = els.runSelect.value || null;
  resetState(true);
});

async function bootstrap() {
  await loadRuns();
  render();
  setInterval(loadRuns, 12000);
  setInterval(pollEvents, 1000);
}

window.addEventListener("resize", () => {
  render();
});

bootstrap();
