// 入口：bridge 就绪 → tab 路由 → 挂载设置/状态模块。
// 主题由 SDK 依 isDark 自动维护 <html data-theme>，此处不重复设置。
import { mountSettings } from "./settings.js";
import { mountStatus } from "./status.js";

const bridge = window.AstrBotPluginPage;

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;            // textContent：不注入 HTML
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 3000);
}

function setupTabs() {
  const ts = document.getElementById("tab-settings");
  const tt = document.getElementById("tab-status");
  const ps = document.getElementById("panel-settings");
  const pt = document.getElementById("panel-status");
  ts.onclick = () => { ts.classList.add("active"); tt.classList.remove("active"); ps.hidden = false; pt.hidden = true; };
  tt.onclick = () => { tt.classList.add("active"); ts.classList.remove("active"); pt.hidden = false; ps.hidden = true; mountStatus(bridge, pt, toast); };
}

async function main() {
  if (bridge && bridge.ready) { await bridge.ready(); }
  setupTabs();
  mountSettings(bridge, document.getElementById("panel-settings"), toast);
}

main();
