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
  wrap.appendChild(input);
  return { wrap, input };
}

function checkboxField(label, checked) {
  const wrap = el("div");
  const lbl = el("label", { text: label });
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = !!checked;
  lbl.prepend(input);            // 复选框在标签文本前
  wrap.appendChild(lbl);
  return { wrap, input };
}

function deleteButton(card) {
  const b = el("button", { class: "danger", text: "删除" });
  b.onclick = () => card.remove();
  return b;
}

// 敏感字段收集：新建行（无 __row_id）留空 = 无明文（""）；既有行留空 = 保留旧值（哨兵）。
// 用户输入的字面量哨兵一律拒绝（否则真实密码等于哨兵会被误判为“未改动”）。
function collectSecret(input, isNew, label) {
  const v = input.value;
  if (v === SENTINEL) throw new Error(`${label}不能为保留字 __unchanged__`);
  if (v !== "") return v;
  return isNew ? "" : SENTINEL;
}

function serverCard(s) {
  const card = el("div", { class: "card" });
  card.dataset.rowId = s.__row_id ?? "";
  const inputs = {};
  for (const key of ["name", "base_url", "username", "timeout", "timezone", "password_env"]) {
    const f = field(key, s[key]);
    inputs[key] = f.input; card.appendChild(f.wrap);
  }
  // enabled / verify_tls：缺省 true（与 parse_config 默认一致），据配置原值初始化
  const enabledF = checkboxField("enabled", s.enabled !== false);
  const verifyF = checkboxField("verify_tls", s.verify_tls !== false);
  card.appendChild(enabledF.wrap);
  card.appendChild(verifyF.wrap);
  // 密码：不预填明文；据 password_set 显示占位
  const pf = field("password", "", {
    type: "password",
    placeholder: s.password_set ? "已设置（留空保持不变）" : "未设置",
  });
  inputs.password = pf.input; card.appendChild(pf.wrap);
  card.appendChild(deleteButton(card));
  card._collect = () => {
    const isNew = !card.dataset.rowId;
    const out = { __row_id: card.dataset.rowId || null };
    for (const [k, inp] of Object.entries(inputs)) {
      if (k === "password") out.password = collectSecret(inp, isNew, "密码");
      else out[k] = inp.value;
    }
    out.enabled = enabledF.input.checked;
    out.verify_tls = verifyF.input.checked;
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
  // 值：不预填明文；据 value_set 显示占位；空输入=保留旧值（既有行）或无明文（新建行）
  const vf = field("value", "", {
    type: "password",
    placeholder: h.value_set ? "已设置（留空保持不变）" : "未设置",
  });
  inputs.value = vf.input; card.appendChild(vf.wrap);
  card.appendChild(deleteButton(card));
  card._collect = () => {
    const isNew = !card.dataset.rowId;
    const out = { __row_id: card.dataset.rowId || null };
    for (const [k, inp] of Object.entries(inputs)) {
      if (k === "value") out.value = collectSecret(inp, isNew, "请求头值");
      else out[k] = inp.value;
    }
    return out;
  };
  return card;
}

function addButton(label, wrap, makeCard) {
  const b = el("button", { text: label });
  b.onclick = () => wrap.appendChild(makeCard({}));
  return b;
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
  root.appendChild(addButton("+ 添加服务器", serversWrap, serverCard));

  const headersWrap = el("div");
  (cfg.custom_headers || []).forEach(h => headersWrap.appendChild(headerCard(h)));
  root.appendChild(el("h3", { text: "自定义请求头" }));
  root.appendChild(headersWrap);
  root.appendChild(addButton("+ 添加请求头", headersWrap, headerCard));

  const save = el("button", { class: "primary", text: "保存并重载" });
  save.onclick = async () => {
    // 收集可能抛错（用户输入了字面量哨兵）——先收集，失败即提示返回
    let servers, headers;
    try {
      servers = Array.from(serversWrap.children)
        .filter(c => c._collect).map(c => c._collect());
      headers = Array.from(headersWrap.children)
        .filter(c => c._collect).map(c => c._collect());
    } catch (e) {
      toast(e.message || "输入不合法");
      return;
    }
    // 其余节（routing/polling/... group_bindings）原样透传保留原值
    const body = { ...cfg };
    body.servers = servers;
    body.custom_headers = headers;
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
    unauthorized: "未登录或登录已过期",
  };
  return (map[res.error] || "保存失败") + path;
}
