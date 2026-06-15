// guest.js — guest mode. Tournaments live only in this browser's localStorage;
// tapping a card goes straight to Tabbycat, so the private key never touches our
// server. window.CompassScan (qr-scan.js) provides optional QR scanning.
(function () {
  var KEY = "compass_guest_tournaments";
  var listEl = document.getElementById("guest-list");
  var emptyEl = document.getElementById("guest-empty");
  var countEl = document.getElementById("guest-count");
  var urlEl = document.getElementById("guest-url");
  var errEl = document.getElementById("guest-error");
  var addBox = document.getElementById("guest-add");

  var T = window.COMPASS_I18N || {};
  var LANG = T.lang || "en";
  function t(key, fallback) { return T[key] || fallback; }
  function countWord(n) {
    var one = t("one", "tournament"), few = t("few", "tournaments"), many = t("many", "tournaments");
    if (LANG === "sk") return n === 1 ? one : n < 5 ? few : many;
    return n === 1 ? one : few; // english: 1 vs many
  }

  var CHEVRON =
    '<svg width="17" height="17" viewBox="0 0 16 16" fill="none">' +
    '<path d="M6 3l5 5-5 5" stroke="#b8c4bc" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round"/></svg>';

  function loadItems() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; }
  }
  function saveItems(items) { localStorage.setItem(KEY, JSON.stringify(items)); }

  function parse(raw) {
    var u;
    try { u = new URL((raw || "").trim()); } catch (e) {
      throw new Error(t("invalidLink", "That doesn't look like a valid link."));
    }
    var seg = u.pathname.split("/").filter(Boolean);
    var i = seg.indexOf("privateurls");
    if (i < 1 || i + 1 >= seg.length) {
      throw new Error(t("notPrivateUrl", "That doesn't look like a Tabbycat private URL."));
    }
    return { slug: seg[i - 1], url: "https://" + u.host + u.pathname };
  }

  function showError(msg) { errEl.textContent = msg; errEl.hidden = false; }

  function render() {
    var items = loadItems();
    listEl.innerHTML = "";
    countEl.textContent = items.length ? items.length + " " + countWord(items.length) : "";
    emptyEl.hidden = items.length > 0;

    items.forEach(function (it, idx) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.className = "tournament";
      a.href = it.url;
      a.rel = "noopener";
      a.innerHTML =
        '<span class="status-dot"><span></span></span>' +
        '<span class="tournament-body">' +
        '<span class="tournament-name"></span>' +
        '<span class="tournament-meta"></span>' +
        "</span>" +
        '<button class="row-del" type="button">✕</button>' +
        '<span class="chevron">' + CHEVRON + "</span>";
      a.querySelector(".tournament-name").textContent = it.name || it.slug;
      a.querySelector(".tournament-meta").textContent = t("savedHere", "Saved on this device");
      a.querySelector(".row-del").setAttribute("aria-label", t("remove", "Remove"));
      a.querySelector(".row-del").addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var items2 = loadItems();
        items2.splice(idx, 1);
        saveItems(items2);
        render();
      });
      li.appendChild(a);
      listEl.appendChild(li);
    });
  }

  function add(raw) {
    var parsed;
    try { parsed = parse(raw); } catch (e) { showError(e.message); return; }
    var items = loadItems();
    if (!items.some(function (x) { return x.url === parsed.url; })) {
      items.push({ name: parsed.slug, slug: parsed.slug, url: parsed.url, added: Date.now() });
      saveItems(items);
    }
    errEl.hidden = true;
    urlEl.value = "";
    addBox.hidden = true;
    render();
  }

  document.getElementById("add-toggle").addEventListener("click", function () {
    addBox.hidden = !addBox.hidden;
    if (!addBox.hidden) urlEl.focus();
  });
  document.getElementById("guest-save").addEventListener("click", function () { add(urlEl.value); });
  urlEl.addEventListener("keydown", function (e) { if (e.key === "Enter") add(urlEl.value); });
  document.getElementById("guest-scan").addEventListener("click", function () {
    window.CompassScan.start(function (text) { urlEl.value = text; add(text); }, showError);
  });

  render();
})();
