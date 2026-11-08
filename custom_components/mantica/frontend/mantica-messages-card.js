/*
 * Mantica - messages card. Served by the integration (no separate install).
 *
 *   type: custom:mantica-messages-card
 *   entity: sensor.<...>_messages      # the "Wiadomości" / "Messages" sensor
 *   title: "Wiadomości: Ewa"            # optional
 *   max: 10                             # optional
 *
 * A click opens the message text and marks a new message as read
 * (service mantica.mark_message_read).
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
  .msg { border: 1px solid var(--divider-color); border-radius: 14px; margin-bottom: 12px;
         background: var(--card-background-color); overflow: hidden; }
  .row { display: grid; grid-template-columns: 1fr auto 24px; align-items: center; gap: 12px;
         padding: 16px 14px 16px 20px; cursor: pointer; user-select: none; }
  .row:hover { background: rgba(127,127,127,.06); }
  .who { font-size: 1.12em; color: var(--primary-text-color); overflow-wrap: anywhere; }
  .subj { margin-top: 8px; color: var(--secondary-text-color); overflow-wrap: anywhere; }
  .new .who::before { content: ""; display: inline-block; width: 9px; height: 9px; margin: 0 8px 1px 0;
                      border-radius: 50%; background: var(--primary-color); }
  .new .subj { color: var(--primary-text-color); font-weight: 600; }
  .date { background: rgba(var(--rgb-primary-color, 3,169,244), .15); color: var(--primary-color);
          font-weight: 700; border-radius: 8px; padding: 5px 12px; white-space: nowrap; }
  svg { width: 24px; height: 24px; fill: var(--secondary-text-color); transition: transform .2s; }
  .open svg { transform: rotate(90deg); }
  .body { padding: 14px 20px 18px; border-top: 1px solid var(--divider-color); white-space: pre-wrap;
          line-height: 1.5; color: var(--primary-text-color); overflow-wrap: anywhere; }
  .muted { color: var(--secondary-text-color); font-style: italic; }
  .meta { margin-top: 12px; font-size: .9em; color: var(--secondary-text-color); }
  .empty { padding: 8px 4px 12px; color: var(--secondary-text-color); }
`;

class ManticaMessagesCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("Podaj entity: sensor Wiadomości z integracji Mantica");
    this._config = { title: "Wiadomości", max: 10, ...config };
    this._open = this._open || new Set();
    this._read = this._read || new Set(); // marked in this view, before the sensor updates
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
    return 2 + Math.min(this._config?.max || 10, 10);
  }

  static getStubConfig(hass) {
    const id = Object.keys(hass.states).find(
      (e) => e.startsWith("sensor.") && e.includes("mantica") && e.endsWith("_messages")
    );
    return { entity: id || "sensor.dziennik_mantica_messages" };
  }

  _el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  _markRead(id) {
    this._read.add(id);
    this._hass.callService("mantica", "mark_message_read", id ? { message_id: id } : {});
  }

  _render() {
    if (!this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const root = this.shadowRoot;
    root.innerHTML = "";
    const style = this._el("style");
    style.textContent = STYLE;
    root.appendChild(style);
    const card = this._el("ha-card");
    root.appendChild(card);

    const st = this._state;
    const all = (st && st.attributes.messages) || [];
    const messages = all.slice(0, this._config.max);
    const isNew = (m) => m.new && !this._read.has(m.id);
    const newCount = all.filter(isNew).length;

    const head = this._el("div", "head");
    head.appendChild(this._el("div", "title", this._config.title));
    if (newCount) {
      const btn = this._el("button", "all");
      btn.title = "Oznacz wszystkie jako przeczytane";
      const icon = this._el("ha-icon");
      icon.setAttribute("icon", "mdi:email-check-outline");
      btn.appendChild(icon);
      btn.addEventListener("click", () => {
        all.forEach((m) => this._read.add(m.id));
        this._markRead(null);
        this._render();
      });
      head.appendChild(btn);
    }
    head.appendChild(this._el("div", "count", `${newCount} / ${all.length}`));
    card.appendChild(head);

    if (!st) {
      card.appendChild(this._el("div", "empty", `Nie znaleziono encji ${this._config.entity}`));
      return;
    }
    if (st.state === "unavailable") {
      card.appendChild(this._el("div", "empty", "Dziennik chwilowo niedostępny"));
      return;
    }
    if (!messages.length) {
      card.appendChild(this._el("div", "empty", "Brak wiadomości"));
      return;
    }

    for (const m of messages) {
      const open = this._open.has(m.id);
      const box = this._el("div", "msg" + (isNew(m) ? " new" : "") + (open ? " open" : ""));
      const row = this._el("div", "row");
      const text = this._el("div");
      text.appendChild(this._el("div", "who", m.sender || "—"));
      text.appendChild(this._el("div", "subj", (m.has_attachment ? "📎 " : "") + (m.subject || "(bez tematu)")));
      row.appendChild(text);
      row.appendChild(this._el("div", "date", (m.received || "").slice(0, 10)));
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 24 24");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", CHEVRON);
      svg.appendChild(path);
      row.appendChild(svg);
      row.addEventListener("click", () => {
        if (this._open.has(m.id)) this._open.delete(m.id);
        else {
          this._open.add(m.id);
          if (isNew(m)) this._markRead(m.id);
        }
        this._render();
      });
      box.appendChild(row);

      if (open) {
        const body = this._el("div", "body");
        if (m.body === null || m.body === undefined) {
          body.appendChild(this._el("span", "muted", "Treść jeszcze nie pobrana - pojawi się po kolejnym odczycie dziennika."));
        } else if (!m.body) {
          body.appendChild(this._el("span", "muted", "(brak treści)"));
        } else {
          body.appendChild(document.createTextNode(m.body));
        }
        const meta = this._el("div", "meta", (m.received || "").slice(0, 16) + (m.has_attachment ? " · załącznik w dzienniku" : ""));
        body.appendChild(meta);
        box.appendChild(body);
      }
      card.appendChild(box);
    }
  }
}

if (!customElements.get("mantica-messages-card")) {
  customElements.define("mantica-messages-card", ManticaMessagesCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "mantica-messages-card",
    name: "Mantica - wiadomości",
    description: "Lista wiadomości z dziennika; kliknięcie pokazuje treść i oznacza wiadomość jako przeczytaną.",
  });
}
