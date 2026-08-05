(() => {
  const $ = (id) => document.getElementById(id);
  const API = "/api/register";
  const state = { directResults: [] };

  const DRAFT_KEYS = {
    directProxy1: "gpt-link:direct-proxy1",
    directProxy2: "gpt-link:direct-proxy2",
    directMaxAttempts: "gpt-link:direct-max-attempts",
  };

  function toast(message, kind = "ok") {
    const host = $("toastHost");
    const node = document.createElement("div");
    node.className = `toast ${kind}`;
    node.textContent = message;
    host.appendChild(node);
    setTimeout(() => node.remove(), 2800);
  }

  function setStatus(text) {
    $("statusText").textContent = text;
  }

  function log(message) {
    const box = $("logBox");
    const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    box.textContent += `\n[${ts}] ${message}`;
    box.scrollTop = box.scrollHeight;
  }

  async function copyText(text, message = "已复制") {
    if (!text) return toast("没有可复制的内容", "err");
    try {
      await navigator.clipboard.writeText(text);
      toast(message);
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      toast(message);
    }
  }

  async function api(path, body) {
    const res = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function apiGet(path) {
    const res = await fetch(API + path, { cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function uiSettingsPayload() {
    return {
      direct_proxy1: $("proxy1").value || "",
      direct_proxy2: $("proxy2").value || "",
      direct_max_attempts: $("directMaxAttempts").value || "20",
    };
  }

  function applyUiSettings(settings) {
    if (!settings || typeof settings !== "object") return;
    if (settings.direct_proxy1 && !$("proxy1").value.trim()) $("proxy1").value = settings.direct_proxy1;
    if (settings.direct_proxy2 && !$("proxy2").value.trim()) $("proxy2").value = settings.direct_proxy2;
    if (settings.direct_max_attempts) $("directMaxAttempts").value = settings.direct_max_attempts;
  }

  async function loadUiSettings() {
    try {
      const data = await apiGet("/ui-settings");
      applyUiSettings(data.settings || {});
      log("已恢复本机代理池设置");
    } catch (err) {
      log(`代理池恢复失败: ${err.message}`);
    }
  }

  async function saveUiSettings(silent = true) {
    try {
      await api("/ui-settings", uiSettingsPayload());
      if (!silent) toast("代理池已保存");
    } catch (err) {
      if (!silent) toast(err.message, "err");
      log(`代理池保存失败: ${err.message}`);
    }
  }

  function debounce(fn, wait = 500) {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }

  const saveUiSettingsSoon = debounce(() => saveUiSettings(true), 500);

  function restoreDrafts() {
    try {
      $("proxy1").value = localStorage.getItem(DRAFT_KEYS.directProxy1) || $("proxy1").value || "";
      $("proxy2").value = localStorage.getItem(DRAFT_KEYS.directProxy2) || $("proxy2").value || "";
      $("directMaxAttempts").value = localStorage.getItem(DRAFT_KEYS.directMaxAttempts) || $("directMaxAttempts").value || "20";
    } catch {
      // Keep the form usable even if localStorage is unavailable.
    }
  }

  function saveDrafts() {
    try {
      localStorage.setItem(DRAFT_KEYS.directProxy1, $("proxy1").value || "");
      localStorage.setItem(DRAFT_KEYS.directProxy2, $("proxy2").value || "");
      localStorage.setItem(DRAFT_KEYS.directMaxAttempts, $("directMaxAttempts").value || "20");
    } catch {
      // Tokens are intentionally not stored; proxy drafts are only a convenience.
    }
    saveUiSettingsSoon();
  }

  async function createShortLink() {
    const token = $("accessToken").value.trim();
    if (!token) return toast("请先粘贴 Session JSON 或 accessToken", "err");
    const maxAttempts = Math.max(1, Math.min(Number($("directMaxAttempts").value || 20), 200));
    const targetAmount = $("directTargetAmount").value.trim() || "0";
    saveDrafts();
    saveUiSettings(true);
    setStatus("单独提链 PH 0 短链");
    log(`开始单独提链 PLUS · PH_SHORT · 目标今日应付 ${targetAmount} · 单账号最多 ${maxAttempts} 次`);
    $("btnShortLink").disabled = true;
    try {
      const data = await api("/short-link-batch", {
        access_token: token,
        country: "PH",
        currency: "PHP",
        mode: "hosted",
        checkout_ui_mode: "hosted",
        plan_name: $("planName").value || "chatgptplusplan",
        use_promo: Boolean($("usePromo").checked),
        target_amount: targetAmount,
        max_attempts: maxAttempts,
        proxy1: $("proxy1").value.trim() || "",
        proxy2: $("proxy2").value.trim() || "",
      });
      state.directResults = Array.isArray(data.results) ? data.results : [];
      const firstOk = state.directResults.find((item) => item.ok && (item.short_url || item.external_url || item.stripe_hosted_url));
      if (firstOk) {
        $("shortUrl").value = firstOk.short_url || "";
        $("externalUrl").value = firstOk.external_url || "";
        $("stripeHostedUrl").value = firstOk.stripe_hosted_url || "";
        const amountText = `${firstOk.amount || "-"} ${firstOk.currency || "PHP"}`;
        $("amountInfo").value = `PLUS · PH_SHORT · 今日应付 ${amountText} · ${firstOk.amount_check || "-"} · 第 ${firstOk.attempt || 1} 次`;
      } else {
        $("shortUrl").value = "";
        $("externalUrl").value = "";
        $("stripeHostedUrl").value = "";
        $("amountInfo").value = "没有成功的 0 链";
      }
      const lines = state.directResults.map((item) => {
        const label = item.account_email || `第 ${item.index || "-"} 条`;
        if (!item.ok) return `[失败] ${label} · ${item.error || "-"}`;
        const link = item.short_url || item.external_url || item.stripe_hosted_url || "-";
        return `[成功] ${label} · ${item.amount || "-"} ${item.currency || "PHP"} · 第 ${item.attempt || 1} 次 · ${link}`;
      });
      $("directBatchResults").value = lines.join("\n");
      log(`单独提链完成：成功 ${data.success || 0}/${data.total || state.directResults.length}，失败 ${data.failed || 0}`);
      setStatus("单独提链完成");
      toast(`成功 ${data.success || 0} 条`);
    } catch (err) {
      log(`单独提链失败: ${err.message}`);
      setStatus("单独提链失败");
      toast(err.message, "err");
    } finally {
      $("btnShortLink").disabled = false;
    }
  }

  function copyDirectSuccessLinks() {
    const links = (state.directResults || [])
      .filter((item) => item && item.ok)
      .map((item) => item.short_url || item.external_url || item.stripe_hosted_url || "")
      .filter(Boolean);
    if (!links.length) {
      const fallback = $("shortUrl").value.trim();
      if (fallback) links.push(fallback);
    }
    copyText(links.join("\n"), "全部成功短链已复制");
  }

  function bind() {
    $("btnShortLink").addEventListener("click", createShortLink);
    $("btnCopyShort").addEventListener("click", () => copyText($("shortUrl").value, "短链已复制"));
    $("btnCopyExternal").addEventListener("click", () => copyText($("externalUrl").value, "外链已复制"));
    $("btnCopyDirectAll").addEventListener("click", copyDirectSuccessLinks);
    ["proxy1", "proxy2", "directMaxAttempts"].forEach((id) => $(id).addEventListener("input", saveDrafts));
    window.addEventListener("beforeunload", () => {
      try {
        const body = JSON.stringify(uiSettingsPayload());
        if (navigator.sendBeacon) {
          navigator.sendBeacon(`${API}/ui-settings`, new Blob([body], { type: "application/json" }));
        }
      } catch {
        // Best effort during page unload.
      }
    });
  }

  restoreDrafts();
  loadUiSettings();
  bind();
})();
