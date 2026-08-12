/* The mixing lab: sliders → websocket → live formula → autosave.
 *
 * Every slider gesture sends the whole mix; the server answers with the
 * derived stats (volume, ABV, cost, standard drinks) and whether it saved.
 * Classics answer but never save — fork to keep your remix. */

(function () {
  "use strict";

  const mixer = document.getElementById("mixer");
  if (!mixer) return;
  const cocktailId = parseInt(mixer.dataset.cocktailId, 10);
  const editable = mixer.dataset.editable === "1";
  const idleState = editable ? "every move is saved 🍸" : "playing — fork to save 🍴";

  let ws = null;
  let retryMs = 1000;
  let timer = null;

  function put(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function setState(text) {
    put("save-state", text);
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(proto + "://" + location.host + "/ws");
    ws.onopen = function () {
      retryMs = 1000;
      setState(idleState);
    };
    ws.onclose = function () {
      setState("connection lost — retrying…");
      setTimeout(connect, retryMs);
      retryMs = Math.min(retryMs * 2, 15000);
    };
    ws.onmessage = function (event) {
      const msg = JSON.parse(event.data);
      if (!msg.ok) {
        setState("⚠ " + msg.error);
        return;
      }
      const stats = msg.stats;
      put("stat-volume", stats.volume + " ml");
      put("stat-abv", stats.abv + "% vol");
      put("stat-cost", "€ " + stats.cost.toFixed(2));
      put("stat-drinks", stats.drinks);
      const fill = document.getElementById("abv-fill");
      if (fill) fill.style.width = Math.min(100, (stats.abv * 100) / 40) + "%";
      setState(msg.saved ? "saved ✓" : idleState);
    };
  }

  function sendMix() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const qtys = {};
    document.querySelectorAll("input.dose").forEach(function (el) {
      qtys[el.dataset.ingredient] = parseFloat(el.value) || 0;
    });
    ws.send(JSON.stringify({ cocktail_id: cocktailId, qtys: qtys }));
  }

  document.addEventListener("input", function (event) {
    const el = event.target;
    if (!el.classList || !el.classList.contains("dose")) return;
    put("dose-" + el.dataset.ingredient, el.value + " ml");
    setState("mixing…");
    clearTimeout(timer);
    timer = setTimeout(sendMix, 200);
  });

  /* After HTMX swaps the mixer (ingredient added or removed), refresh stats. */
  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail && event.detail.target && event.detail.target.id === "mixer") {
      sendMix();
    }
  });

  connect();
})();
