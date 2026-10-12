(function () {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.disableVerticalSwipes?.(); } catch (_) {}
  }

  const state = {
    me: null,
    sectionId: null,
    productId: null,
    history: ["home"],
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  function authHeader() {
    const initData = tg?.initData || "";
    return { Authorization: "tma " + initData };
  }

  async function api(path, opts = {}) {
    const headers = { ...authHeader(), ...(opts.headers || {}) };
    if (opts.body && typeof opts.body === "object") {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, { ...opts, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.detail || data.message || res.statusText || "Error";
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }

  function showLoader(on) {
    $("#loader").classList.toggle("hidden", !on);
  }

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.add("hidden"), 2200);
  }

  function setTitle(t) {
    $("#page-title").textContent = t;
  }

  function showScreen(name, push = true) {
    $$(".screen").forEach((s) => s.classList.remove("active"));
    const el = $(`#screen-${name}`);
    if (el) el.classList.add("active");

    if (push) {
      const last = state.history[state.history.length - 1];
      if (last !== name) state.history.push(name);
    }
    const canBack = state.history.length > 1 && name !== "home";
    $("#btn-back").classList.toggle("hidden", !canBack);

    const titles = {
      home: state.me?.shop_name || "Магазин",
      catalog: "Каталог",
      products: "Товары",
      product: "Товар",
      success: "Готово",
      profile: "Профиль",
      orders: "Покупки",
      reviews: "Отзывы",
      info: "Правила",
      support: "Поддержка",
    };
    setTitle(titles[name] || "Магазин");

    if (tg) {
      if (name === "home") {
        tg.BackButton.hide();
      } else {
        tg.BackButton.show();
      }
    }
  }

  function goBack() {
    if (state.history.length <= 1) return;
    state.history.pop();
    const prev = state.history[state.history.length - 1];
    showScreen(prev, false);
  }

  // ---- data loaders ----
  async function loadMe() {
    state.me = await api("/api/me");
    $("#balance-text").textContent = state.me.balance_fmt;
    $("#shop-name").textContent = state.me.shop_name;
    setTitle(state.me.shop_name);
  }

  async function loadSections() {
    showLoader(true);
    try {
      const rows = await api("/api/sections");
      const list = $("#sections-list");
      list.innerHTML = "";
      $("#catalog-empty").classList.toggle("hidden", rows.length > 0);
      rows.forEach((s) => {
        const div = document.createElement("div");
        div.className = "list-item";
        div.innerHTML = `
          <div>
            <div class="title">📂 ${esc(s.name)}</div>
            <div class="meta">${s.count} в наличии</div>
          </div>
          <span class="badge">${s.count}</span>`;
        div.onclick = () => openSection(s.id, s.name);
        list.appendChild(div);
      });
    } finally {
      showLoader(false);
    }
  }

  async function openSection(id, name) {
    state.sectionId = id;
    showScreen("products");
    setTitle(name || "Товары");
    showLoader(true);
    try {
      const rows = await api(`/api/products?section_id=${id}`);
      const list = $("#products-list");
      list.innerHTML = "";
      $("#products-empty").classList.toggle("hidden", rows.length > 0);
      rows.forEach((p) => {
        const div = document.createElement("div");
        div.className = "list-item";
        const stockBadge = p.in_stock
          ? `<span class="badge">${p.stock} шт</span>`
          : `<span class="badge out">Нет</span>`;
        div.innerHTML = `
          <div>
            <div class="title">${esc(p.name)}</div>
            <div class="meta">${esc((p.descr || "").slice(0, 60))}</div>
          </div>
          <div class="right">
            <div class="price">${p.price_fmt}</div>
            ${stockBadge}
          </div>`;
        div.onclick = () => openProduct(p.id);
        list.appendChild(div);
      });
    } finally {
      showLoader(false);
    }
  }

  async function openProduct(id) {
    state.productId = id;
    showScreen("product");
    showLoader(true);
    try {
      const p = await api(`/api/product/${id}`);
      $("#prod-name").textContent = p.name;
      $("#prod-descr").textContent = p.descr || "";
      $("#prod-price").textContent = p.price_fmt;
      $("#prod-stock").textContent = p.in_stock ? `${p.stock} шт` : "Нет в наличии";
      const btn = $("#btn-buy");
      btn.disabled = !p.in_stock;
      btn.textContent = p.in_stock ? "🛒 Купить" : "Нет в наличии";
      $("#buy-error").classList.add("hidden");
    } finally {
      showLoader(false);
    }
  }

  async function doBuy() {
    const btn = $("#btn-buy");
    btn.disabled = true;
    $("#buy-error").classList.add("hidden");
    showLoader(true);
    try {
      const res = await api("/api/buy", {
        method: "POST",
        body: { product_id: state.productId },
      });
      $("#success-name").textContent = `${res.product_name} — ${res.price_fmt}`;
      $("#success-content").textContent = res.content || "(пусто)";
      $("#balance-text").textContent = res.new_balance_fmt;
      if (state.me) {
        state.me.balance = res.new_balance;
        state.me.balance_fmt = res.new_balance_fmt;
      }
      showScreen("success");
      if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
    } catch (e) {
      $("#buy-error").textContent = e.message;
      $("#buy-error").classList.remove("hidden");
      btn.disabled = false;
      if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred("error");
    } finally {
      showLoader(false);
    }
  }

  async function loadProfile() {
    await loadMe();
    $("#prof-name").textContent = state.me.name || "—";
    $("#prof-id").textContent = `ID: ${state.me.id}` + (state.me.username ? ` · @${state.me.username}` : "");
    $("#prof-bal").textContent = state.me.balance_fmt;
    $("#prof-orders").textContent = state.me.orders_count;
  }

  async function loadOrders() {
    showLoader(true);
    try {
      const rows = await api("/api/orders");
      const list = $("#orders-list");
      list.innerHTML = "";
      $("#orders-empty").classList.toggle("hidden", rows.length > 0);
      rows.forEach((o) => {
        const div = document.createElement("div");
        div.className = "list-item";
        div.style.cursor = "default";
        div.innerHTML = `
          <div>
            <div class="title">#${o.id} · ${esc(o.product_name)}</div>
            <div class="meta">${o.date}</div>
          </div>
          <div class="price">${o.price_fmt}</div>`;
        list.appendChild(div);
      });
    } finally {
      showLoader(false);
    }
  }

  async function loadReviews() {
    showLoader(true);
    try {
      const rows = await api("/api/reviews");
      const list = $("#reviews-list");
      list.innerHTML = "";
      $("#reviews-empty").classList.toggle("hidden", rows.length > 0);
      rows.forEach((r) => {
        const div = document.createElement("div");
        div.className = "list-item";
        div.style.cursor = "default";
        div.innerHTML = `
          <div>
            <div class="title">⭐ ${esc(r.author)}</div>
            <div class="meta">${esc(r.text)}</div>
            <div class="meta" style="margin-top:4px">${r.date}</div>
          </div>`;
        list.appendChild(div);
      });
    } finally {
      showLoader(false);
    }
  }

  async function loadInfo() {
    const info = await api("/api/info");
    $("#rules-text").textContent = info.rules;
    $("#faq-text").textContent = info.faq;
  }

  function loadSupport() {
    const s = state.me?.support || "@support";
    const link = $("#support-link");
    const uname = s.replace(/^@/, "");
    link.href = `https://t.me/${uname}`;
    link.textContent = s;
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  // ---- navigation ----
  $$(".nav-card").forEach((btn) => {
    btn.onclick = async () => {
      const go = btn.dataset.go;
      showScreen(go);
      if (go === "catalog") await loadSections();
      if (go === "profile") await loadProfile();
      if (go === "orders") await loadOrders();
      if (go === "reviews") await loadReviews();
      if (go === "info") await loadInfo();
      if (go === "support") loadSupport();
    };
  });

  $("#btn-back").onclick = goBack;
  if (tg) {
    tg.BackButton.onClick(goBack);
  }

  $("#btn-buy").onclick = doBuy;

  $("#btn-copy").onclick = () => {
    const text = $("#success-content").textContent;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => toast("Скопировано"));
    } else {
      toast("Скопируйте вручную");
    }
  };

  $("#btn-to-home").onclick = () => {
    state.history = ["home"];
    showScreen("home", false);
  };

  $("#btn-open-bot").onclick = () => {
    if (tg) tg.close();
    else window.open("https://t.me/", "_blank");
  };

  // ---- init ----
  (async function init() {
    showLoader(true);
    try {
      if (!tg?.initData) {
        // dev mode without Telegram
        console.warn("No Telegram initData — running in demo mode");
      }
      await loadMe();
      showScreen("home", false);
      state.history = ["home"];
    } catch (e) {
      console.error(e);
      toast("Ошибка авторизации: " + e.message);
      setTitle("Ошибка");
    } finally {
      showLoader(false);
    }
  })();
})();
