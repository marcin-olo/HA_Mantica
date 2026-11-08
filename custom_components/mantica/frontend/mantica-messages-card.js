/*
 * Mantica - messages card. Served by the integration (no separate install).
 *
 *   type: custom:mantica-messages-card
 *   entity: sensor.<...>_messages      # the "Wiadomości" / "Messages" sensor
 *   title: "Wiadomości: Ewa"            # optional
 *   max: 3                              # optional, how many latest messages
 *
 * New messages are bold. A click opens the full text in a popup and marks
 * the message as read (service mantica.mark_message_read).
 */
const CHEVRON = "M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z";

const STYLE = `
  ha-card { padding: 20px 16px 12px; text-align: start; }
  .head { display: flex; align-items: center; gap: 8px; padding: 0 4px 12px;
          border-bottom: 3px solid var(--primary-color); margin-bottom: 14px; }
  .title { flex: 1; font-size: 1.45em; font-weight: 500; color: var(--primary-text-color); }
  .count { color: var(--primary-color); font-weight: 700; font-size: 1.15em; white-space: nowrap; }
  .all { background: none; border: 0; padding: 4px; cursor: pointer; color: var(--primary-color);
         border-radius: 50%; display: flex; }
  .all:hover { background: rgba(127,127,127,.15); }
  .msg { display: grid; grid-template-columns: 1fr auto 24px; align-items: center; gap: 12px;
         padding: 16px 14px 16px 20px; margin-bottom: 12px; cursor: pointer; user-select: none;
         border: 1px solid var(--divider-color); border-radius: 14px;
         background: var(--card-background-color); }
  .msg:hover { background: rgba(127,127,127,.06); }
  .who { font-size: 1.12em; color: var(--primary-text-color); overflow-wrap: anywhere; }
  .subj { margin-top: 8px; color: var(--secondary-text-color); overflow-wrap: anywhere; }
  .new .who, .new .subj { font-weight: 700; color: var(--primary-text-color); }
  .date { background: rgba(var(--rgb-primary-color, 3,169,244), .15); color: var(--primary-color);
          font-weight: 700; border-radius: 8px; padding: 5px 12px; white-space: nowrap; }
  svg { width: 24px; height: 24px; fill: var(--secondary-text-color); }
  .empty { padding: 8px 4px 12px; color: var(--secondary-text-color); }
`;

// The popup lives in document.body (a native <dialog> in the top layer), so
// dashboard layouts cannot clip it; its styles are therefore inline.
const POPUP_STYLE = `
  .mantica-popup { border: 0; padding: 0; border-radius: 16px; width: min(560px, 92vw);
    max-height: 85vh; background: var(--card-background-color, #1c1c1c);
    color: var(--primary-text-color, #e1e1e1); box-shadow: 0 8px 32px rgba(0,0,0,.45);
    font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); text-align: start; }
  .mantica-popup::backdrop { background: rgba(0,0,0,.55); }
  .mantica-popup .p-head { padding: 20px 22px 14px; border-bottom: 3px solid var(--primary-color, #03a9f4); }
  .mantica-popup .p-subj { font-size: 1.25em; font-weight: 600; overflow-wrap: anywhere; }
  .mantica-popup .p-meta { margin-top: 6px; color: var(--secondary-text-color, #9b9b9b); overflow-wrap: anywhere; }
  .mantica-popup .p-body { padding: 18px 22px; white-space: pre-wrap; line-height: 1.55;
    overflow: auto; max-height: calc(85vh - 160px); overflow-wrap: anywhere; }
  .mantica-popup .p-muted { color: var(--secondary-text-color, #9b9b9b); font-style: italic; }
  .mantica-popup .p-foot { display: flex; justify-content: flex-end; padding: 6px 14px 14px; }
  .mantica-popup button { background: none; border: 0; color: var(--primary-color, #03a9f4);
    font-weight: 600; font-size: 1em; padding: 10px 16px; border-radius: 8px; cursor: pointer; }
  .mantica-popup button:hover { background: rgba(127,127,127,.15); }
`;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function openPopup(m) {
  if (!document.getElementById("mantica-popup-style")) {
    const st = el("style");
    st.id = "mantica-popup-style";
    st.textContent = POPUP_STYLE;
    document.head.appendChild(st);
  }
  const dlg = el("dialog", "mantica-popup");
  const head = el("div", "p-head");
  head.appendChild(el("div", "p-subj", (m.has_attachment ? "📎 " : "") + (m.subject || "(bez tematu)")));
  head.appendChild(el("div", "p-meta", `${m.sender || "—"} · ${(m.received || "").slice(0, 16)}`));
  dlg.appendChild(head);
  const body = el("div", "p-body");
  if (m.body === null || m.body === undefined) {
    body.appendChild(el("span", "p-muted", "Treść jeszcze nie pobrana - pojawi się po kolejnym odczycie dziennika."));
  } else if (!m.body) {
    body.appendChild(el("span", "p-muted", "(brak treści)"));
  } else {
    body.textContent = m.body;
  }
  if (m.has_attachment) body.appendChild(el("div", "p-muted", "\nZałącznik dostępny w dzienniku."));
  dlg.appendChild(body);
  const foot = el("div", "p-foot");
  const close = el("button", null, "Zamknij");
  close.addEventListener("click", () => dlg.close());
  foot.appendChild(close);
  dlg.appendChild(foot);
  dlg.addEventListener("click", (ev) => {
    if (ev.target === dlg) dlg.close(); // click on the backdrop
  });
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
}

class ManticaMessagesCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("Podaj entity: sensor Wiadomości z integracji Mantica");
    this._config = { title: "Wiadomości", max: 3, ...config };
    this._read = this._read || new Set(); // marked here, before the sensor updates
    this._state = undefined;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const st = hass.states[this._config.entity];
    if (st !== this._state) {
      this._state = st;
      this._render();
    }
  }

  getCardSize() {
    return 2 + Math.min(this._config?.max || 3, 10);
  }

  static getStubConfig(hass) {
    const id = Object.keys(hass.states).find(
      (e) => e.startsWith("sensor.") && e.includes("mantica") && e.endsWith("_messages")
    );
    return { entity: id || "sensor.dziennik_mantica_messages" };
  }

  _markRead(id) {
    if (id) this._read.add(id);
    this._hass.callService("mantica", "mark_message_read", id ? { message_id: id } : {});
  }

  _render() {
    if (!this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    root.innerHTML = "";
    const style = el("style");
    style.textContent = STYLE;
    root.appendChild(style);
    const card = el("ha-card");
    root.appendChild(card);

    const st = this._state;
    const all = (st && st.attributes.messages) || [];
    const isNew = (m) => m.new && !this._read.has(m.id);
    const newCount = all.filter(isNew).length;

    const head = el("div", "head");
    head.appendChild(el("div", "title", this._config.title));
    if (newCount) {
      const btn = el("button", "all");
      btn.title = "Oznacz wszystkie jako przeczytane";
      const icon = el("ha-icon");
      icon.setAttribute("icon", "mdi:email-check-outline");
      btn.appendChild(icon);
      btn.addEventListener("click", () => {
        all.forEach((m) => this._read.add(m.id));
        this._markRead(null);
        this._render();
      });
      head.appendChild(btn);
    }
    head.appendChild(el("div", "count", `${newCount} / ${all.length}`));
    card.appendChild(head);

    if (!st) {
      card.appendChild(el("div", "empty", `Nie znaleziono encji ${this._config.entity}`));
      return;
    }
    if (st.state === "unavailable") {
      card.appendChild(el("div", "empty", "Dziennik chwilowo niedostępny"));
      return;
    }
    if (!all.length) {
      card.appendChild(el("div", "empty", "Brak wiadomości"));
      return;
    }

    for (const m of all.slice(0, this._config.max)) {
      const row = el("div", "msg" + (isNew(m) ? " new" : ""));
      const text = el("div");
      text.appendChild(el("div", "who", m.sender || "—"));
      text.appendChild(el("div", "subj", (m.has_attachment ? "📎 " : "") + (m.subject || "(bez tematu)")));
      row.appendChild(text);
      row.appendChild(el("div", "date", (m.received || "").slice(0, 10)));
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", CHEVRON);
      svg.appendChild(path);
      row.appendChild(svg);
      row.addEventListener("click", () => {
        openPopup(m);
        if (isNew(m)) {
          this._markRead(m.id);
          this._render();
        }
      });
      card.appendChild(row);
    }
  }
}

if (!customElements.get("mantica-messages-card")) {
  customElements.define("mantica-messages-card", ManticaMessagesCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "mantica-messages-card",
    name: "Mantica - wiadomości",
    description: "Ostatnie wiadomości z dziennika; kliknięcie otwiera treść i oznacza wiadomość jako przeczytaną.",
  });
}
