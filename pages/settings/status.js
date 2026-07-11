// 状态面板：拉取只读状态 → 卡片渲染 → 手动刷新。全部 textContent。
export async function mountStatus(bridge, root, toast) {
  root.replaceChildren();
  const refresh = document.createElement("button");
  refresh.className = "primary";
  refresh.textContent = "刷新";
  const list = document.createElement("div");
  root.appendChild(refresh);
  root.appendChild(list);

  async function load() {
    list.replaceChildren();
    let data;
    try { data = await bridge.apiGet("status/overview"); }
    catch (e) { toast("读取状态失败"); return; }
    if (data.restarting) {
      const p = document.createElement("p");
      p.textContent = "插件正在重载配置…";
      list.appendChild(p);
      setTimeout(load, 3000);
      return;
    }
    for (const row of data.servers) {
      const card = document.createElement("div");
      card.className = "card";
      const title = document.createElement("strong");
      title.textContent = row.name;              // 服务器名：textContent 防 XSS
      card.appendChild(title);
      const line = document.createElement("div");
      if (!row.ready) line.textContent = "未就绪";
      else line.textContent = `在线 ${row.online} · ${row.smoothness_label}` +
        (row.degraded ? " · 数据缺失" : "");
      card.appendChild(line);
      list.appendChild(card);
    }
  }
  refresh.onclick = load;
  load();
}
