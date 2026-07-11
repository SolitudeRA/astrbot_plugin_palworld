// 设置表单：拉取脱敏配置 → 渲染可增删卡片与分组 → 收集提交。
// 一切外部字符串经 textContent/value 写入，绝不用 innerHTML。
const SENTINEL = "__unchanged__";

function el(tag, props = {}, children = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "text") n.textContent = v;         // 安全文本
    else if (k === "value") n.value = v;
    else n.setAttribute(k, v);
  }
  for (const c of children) n.appendChild(c);
  return n;
}

function field(label, value, opts = {}) {
  const wrap = el("div");
  wrap.appendChild(el("label", { text: label }));
  const input = el("input", { value: value ?? "" });
  if (opts.type) input.type = opts.type;
  if (opts.placeholder) input.placeholder = opts.placeholder;
  if (opts.dataset) input.dataset.key = opts.dataset;
  wrap.appendChild(input);
  return { wrap, input };
}

function serverCard(s) {
  const card = el("div", { class: "card" });
  card.dataset.rowId = s.__row_id ?? "";
  const inputs = {};
  for (const key of ["name", "base_url", "username", "timeout", "timezone", "password_env"]) {
    const f = field(key, s[key]);
    inputs[key] = f.input; card.appendChild(f.wrap);
  }
  // 密码：不预填明文；据 password_set 显示占位
  const pf = field("password", "", {
    type: "password",
    placeholder: s.password_set ? "已设置（留空保持不变）" : "未设置",
  });
  inputs.password = pf.input; card.appendChild(pf.wrap);
  card._collect = () => {
    const out = { __row_id: card.dataset.rowId || null };
    for (const [k, inp] of Object.entries(inputs)) {
      if (k === "password") out.password = inp.value === "" ? SENTINEL : inp.value;
      else if (k === "timeout") out.timeout = inp.value;
      else out[k] = inp.value;
    }
    return out;
  };
  return card;
}

function headerCard(h) {
  const card = el("div", { class: "card" });
  card.dataset.rowId = h.__row_id ?? "";
  const inputs = {};
  for (const key of ["name", "value_env", "servers"]) {
    const f = field(key, h[key]);
    inputs[key] = f.input; card.appendChild(f.wrap);
  }
  // 值：不预填明文；据 value_set 显示占位；空输入=保留旧值（哨兵）
  const vf = field("value", "", {
    type: "password",
    placeholder: h.value_set ? "已设置（留空保持不变）" : "未设置",
  });
  inputs.value = vf.input; card.appendChild(vf.wrap);
  card._collect = () => {
    const out = { __row_id: card.dataset.rowId || null };
    for (const [k, inp] of Object.entries(inputs)) {
      if (k === "value") out.value = inp.value === "" ? SENTINEL : inp.value;
      else out[k] = inp.value;
    }
    return out;
  };
  return card;
}

export async function mountSettings(bridge, root, toast) {
  root.replaceChildren();
  let cfg;
  try { const r = await bridge.apiGet("config/get"); cfg = r.config; }
  catch (e) { toast("读取配置失败"); return; }

  const serversWrap = el("div");
  (cfg.servers || []).forEach(s => serversWrap.appendChild(serverCard(s)));
  root.appendChild(el("h3", { text: "服务器" }));
  root.appendChild(serversWrap);

  const headersWrap = el("div");
  (cfg.custom_headers || []).forEach(h => headersWrap.appendChild(headerCard(h)));
  root.appendChild(el("h3", { text: "自定义请求头" }));
  root.appendChild(headersWrap);

  const save = el("button", { class: "primary", text: "保存并重载" });
  save.onclick = async () => {
    // 其余节（routing/polling/... group_bindings）原样透传保留原值；
    // servers/custom_headers 用收集值（含哨兵），避免脱敏空值被判为清空
    const body = { ...cfg };
    body.servers = Array.from(serversWrap.children).map(c => c._collect());
    body.custom_headers = Array.from(headersWrap.children).map(c => c._collect());
    delete body.__row_id;
    try {
      const res = await bridge.apiPost("config/save", body);
      if (res.ok) {
        const w = res.warnings || {};
        const skips = [...(w.skipped_servers || []), ...(w.skipped_headers || [])];
        toast(skips.length ? `已保存（${skips.length} 条被跳过）` : "已保存并重载");
      } else {
        toast(errorText(res));
      }
    } catch (e) { toast("保存失败"); }
  };
  root.appendChild(save);
}

function errorText(res) {
  const path = res.detail && res.detail.path ? `：${res.detail.path}` : "";
  const map = {
    save_in_progress: "保存进行中，请稍候",
    too_frequent: "保存过于频繁，请稍候再试",
    too_large: "配置过大",
    invalid_shape: "配置结构不合法",
    invalid_field: "字段不合法",
    credential_redirect: "修改了服务器地址，请重新输入该服务器密码",
    restart_failed_rolled_back: "重载失败，已回滚到旧配置",
    restart_failed: "重载失败且回滚失败，请检查后台",
  };
  return (map[res.error] || "保存失败") + path;
}
