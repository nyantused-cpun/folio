/* 售前助手 HTML 编辑器（D-091）
 * 工具条：编辑/预览切换 · 配色面板 · 导出 HTML · 重置
 * 无依赖原生 JS；导出优先 File System Access API，降级 Blob 下载。
 */
(function () {
  "use strict";

  var STORAGE_KEY = "__presales_editor_original__";
  var COLOR_KEY = "__presales_editor_colors__";
  var THEME_KEY = "__presales_editor_theme__";

  var COLOR_FIELDS = [
    { key: "primary", label: "主色（标题线/要点/卡片题）", def: "#3182ce" },
    { key: "heading", label: "标题色", def: "#1a365d" },
    { key: "cardBg", label: "卡片底色", def: "#f7fafc" },
    { key: "pageBg", label: "页面背景", def: "#ffffff" }
  ];

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* rgb(a) 转 #rrggbb；透明或无法解析返回 null（交给 COLOR_FIELDS.def 回退） */
  function rgbToHex(rgb) {
    var m = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+)\s*)?\)$/.exec(rgb || "");
    if (!m) return null;
    if (m[4] !== undefined && parseFloat(m[4]) === 0) return null;
    function h(i) { return ("0" + parseInt(m[i], 10).toString(16)).slice(-2); }
    return "#" + h(1) + h(2) + h(3);
  }

  function computedColor(sel, prop) {
    var el = $(sel);
    if (!el || !window.getComputedStyle) return null;
    try { return rgbToHex(window.getComputedStyle(el)[prop]); } catch (e) { return null; }
  }

  /* 面板初值从文档计算样式读（h1/h2/.card-title/.dg-title 等实际色），
   * 而非硬编码 enterprise 默认值；读不到才回退 COLOR_FIELDS.def。
   * 缓存一次：init 后文档样式不变。 */
  var _docColors = null;
  function docColors() {
    if (_docColors) return _docColors;
    _docColors = {
      heading: computedColor("h1", "color") || computedColor("h2", "color") ||
               computedColor(".card-title", "color") || computedColor(".dg-title", "color"),
      primary: computedColor("h1", "borderBottomColor") ||
               computedColor(".pullquote", "borderLeftColor"),
      cardBg: computedColor(".card", "backgroundColor") ||
              computedColor(".phase", "backgroundColor"),
      pageBg: computedColor("body", "backgroundColor")
    };
    return _docColors;
  }

  /* ---------- 编辑模式 ---------- */
  function setMode(mode) {
    document.body.setAttribute("data-edit-mode", mode);
    var on = mode === "edit";
    $all("[data-editable]").forEach(function (el) {
      el.contentEditable = on ? "true" : "false";
      if (on) el.setAttribute("spellcheck", "false");
    });
    var btn = $("#__editor_toolbar [data-action='toggle-edit']");
    if (btn) btn.textContent = on ? "完成编辑" : "编辑";
  }

  /* ---------- 配色 ---------- */
  function currentColors() {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(COLOR_KEY) || "null"); } catch (e) {}
    var doc = docColors();
    var colors = {};
    COLOR_FIELDS.forEach(function (f) {
      colors[f.key] = (saved && saved[f.key]) || doc[f.key] || f.def;
    });
    return colors;
  }

  function applyColors(colors) {
    var css =
      "h1{color:" + colors.heading + "!important;border-bottom-color:" + colors.primary + "!important;}" +
      "h2{color:" + colors.heading + "!important;}" +
      ".dg-title{color:" + colors.heading + "!important;}" +
      ".bullet::before{color:" + colors.primary + "!important;}" +
      ".card-title,.phase-label{color:" + colors.heading + "!important;}" +
      ".card,.phase,.pullquote{background:" + colors.cardBg + "!important;}" +
      ".pullquote{border-left-color:" + colors.primary + "!important;}" +
      "body{background:" + colors.pageBg + "!important;}";
    var tag = $("#__editor_theme");
    if (!tag) {
      tag = document.createElement("style");
      tag.id = "__editor_theme";
      document.head.appendChild(tag);
    }
    tag.textContent = css;
    try { localStorage.setItem(COLOR_KEY, JSON.stringify(colors)); } catch (e) {}
  }

  function buildPanel() {
    var panel = $("#__editor_color_panel");
    if (!panel) return;
    var colors = currentColors();
    panel.innerHTML = "";
    COLOR_FIELDS.forEach(function (f) {
      var row = document.createElement("label");
      row.className = "color-row";
      row.innerHTML = '<input type="color" value="' + colors[f.key] + '"><span>' + f.label + "</span>";
      row.querySelector("input").addEventListener("input", function (ev) {
        var c = currentColors();
        c[f.key] = ev.target.value;
        applyColors(c);
      });
      panel.appendChild(row);
    });
  }

  function togglePanel() {
    var panel = $("#__editor_color_panel");
    if (!panel) return;
    panel.classList.toggle("open");
  }

  /* ---------- 主题切换（v2.0 §9.4：替换 :root 变量块，复用动态样式表机制） ---------- */
  function v2Themes() { return window.__V2_THEMES__ || null; }

  function applyTheme(name) {
    var themes = v2Themes();
    if (!themes || !themes[name]) return;
    var tag = $("#__editor_theme");
    if (!tag) {
      tag = document.createElement("style");
      tag.id = "__editor_theme";
      document.head.appendChild(tag);
    }
    tag.textContent = themes[name];
    try { localStorage.setItem(THEME_KEY, name); } catch (e) {}
  }

  function buildThemePanel() {
    var panel = $("#__editor_color_panel");
    var themes = v2Themes();
    if (!panel || !themes) return;
    var saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) {}
    var current = saved && themes[saved] ? saved : Object.keys(themes)[0];
    panel.innerHTML = "";
    var row = document.createElement("label");
    row.className = "color-row";
    var sel = document.createElement("select");
    Object.keys(themes).forEach(function (name) {
      var opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      if (name === current) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", function (ev) { applyTheme(ev.target.value); });
    row.appendChild(sel);
    row.appendChild(document.createElement("span"));
    row.lastChild.textContent = "主题包（spec 写主题名，此处仅预览切换）";
    panel.appendChild(row);
  }

  /* ---------- 导出 ---------- */
  function cleanClone() {
    var clone = document.documentElement.cloneNode(true);
    var body = clone.querySelector("body");
    if (body) body.setAttribute("data-edit-mode", "preview");
    $all("[data-editable]", clone).forEach(function (el) { el.removeAttribute("contenteditable"); });
    return "<!DOCTYPE html>\n" + clone.outerHTML;
  }

  function exportHTML() {
    var html = cleanClone();
    var name = (document.title || "document").replace(/[\\/:*?"<>|]/g, "_") + ".html";
    if (window.showSaveFilePicker) {
      window.showSaveFilePicker({
        suggestedName: name,
        types: [{ description: "HTML", accept: { "text/html": [".html"] } }]
      }).then(function (handle) {
        return handle.createWritable().then(function (w) {
          return w.write(html).then(function () { return w.close(); });
        });
      }).catch(function () { /* 用户取消 */ });
    } else {
      var blob = new Blob([html], { type: "text/html;charset=utf-8" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
    }
  }

  /* ---------- 重置 ---------- */
  function resetAll() {
    var original = null;
    try { original = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    if (original) {
      document.open();
      document.write(original);
      document.close();
    }
    try {
      localStorage.removeItem(COLOR_KEY);
      localStorage.removeItem(THEME_KEY);
    } catch (e) {}
    location.reload();
  }

  /* ---------- 初始化 ---------- */
  function init() {
    // 快照原始 HTML（首次载入时）
    try {
      if (!localStorage.getItem(STORAGE_KEY)) {
        localStorage.setItem(STORAGE_KEY, "<!DOCTYPE html>\n" + document.documentElement.outerHTML);
      }
    } catch (e) {}

    var toolbar = $("#__editor_toolbar");
    if (!toolbar) return;
    toolbar.addEventListener("click", function (ev) {
      var action = ev.target.getAttribute("data-action");
      if (!action) return;
      if (action === "toggle-edit") {
        setMode(document.body.getAttribute("data-edit-mode") === "edit" ? "preview" : "edit");
      } else if (action === "color-panel" || action === "theme-panel") {
        togglePanel();
      } else if (action === "export") {
        exportHTML();
      } else if (action === "reset") {
        if (confirm("恢复初始状态？全部修改将丢失")) resetAll();
      }
    });

    buildPanel();
    buildThemePanel();
    // 无 saved 配色时不 applyColors：交付 HTML 打开应保持文档原配色
    // （此前无条件用 enterprise 硬编码默认值带 !important 全刷，打开即改色）。
    // 面板初值仍由 currentColors() 填充（文档计算色，取不到回退硬编码）。
    var hasSaved = false;
    try { hasSaved = !!localStorage.getItem(COLOR_KEY); } catch (e) {}
    if (hasSaved) applyColors(currentColors());
    // v2 主题恢复（§9.4）：saved 主题名有效时替换 :root 变量块
    var savedTheme = null;
    try { savedTheme = localStorage.getItem(THEME_KEY); } catch (e) {}
    if (savedTheme) applyTheme(savedTheme);
    setMode("preview");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
