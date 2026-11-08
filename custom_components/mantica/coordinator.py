"""Data coordinator: polls the portal, detects new grades/messages."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import parser
from .api import (
    ManticaAuthError,
    ManticaClient,
    ManticaConnectionError,
    ManticaError,
    ManticaLayoutError,
)
from .const import (
    DOMAIN,
    EVENT_BULK,
    EVENT_NEW_CALENDAR,
    EVENT_NEW_GRADE,
    EVENT_NEW_MESSAGE,
    ISSUE_ICON,
    ISSUE_LAYOUT,
    ISSUE_UNREACHABLE,
    CONF_ACTIVE_FROM,
    CONF_ACTIVE_TO,
    CONF_SCAN_MINUTES,
    DEFAULT_ACTIVE_FROM,
    DEFAULT_ACTIVE_TO,
    DEFAULT_SCAN_MINUTES,
)
from .policy import (
    ACTION_ISSUE,
    ACTION_REAUTH,
    ID_FORMAT,
    FailurePolicy,
    find_new,
    next_poll_delay,
    recently_added,
)

_LOGGER = logging.getLogger(__name__)

GRADE_FIELDS = ("subject", "value", "date", "description", "weight", "teacher")
MESSAGE_FIELDS = ("id", "subject", "sender", "received", "unread", "body")
CALENDAR_FIELDS = ("name", "date", "days_left", "teacher", "description", "added", "is_test")
# Message bodies fetched per update, so a full inbox does not mean 10
# extra requests at once.
MAX_BODY_FETCHES = 5


class ManticaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ManticaClient,
        policy: FailurePolicy,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(minutes=DEFAULT_SCAN_MINUTES),
        )
        self.client = client
        # Kept in hass.data by __init__.py so counts survive reloads/setup retries.
        self.policy = policy
        self._store: Store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")
        self._seen: dict[str, set[str] | None] = {
            "grades": None,
            "messages": None,
            "events": None,
        }
        # Opening a message marks it read on the portal, so "new" is tracked
        # here: ids seen unread on the portal, until marked read in HA.
        self._new_msgs: set[str] = set()
        self._dismissed: set[str] = set()
        self._bodies: dict[str, str] = {}

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        if "messages" in stored:
            self._seen["messages"] = set(stored["messages"])
        if "events" in stored:
            self._seen["events"] = set(stored["events"])
        self._new_msgs = set(stored.get("new_messages", ()))
        self._dismissed = set(stored.get("dismissed_messages", ()))
        self._bodies = dict(stored.get("bodies", {}))
        # Grade IDs changed format in 0.2.0 -> re-seed silently instead of
        # announcing every existing grade as new.
        if stored.get("id_format") == ID_FORMAT and "grades" in stored:
            self._seen["grades"] = set(stored["grades"])

    # -- issues -------------------------------------------------------------
    def _issue(self, issue_id: str, severity: ir.IssueSeverity, **placeholders: str) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{issue_id}_{self.config_entry.entry_id}",
            is_fixable=False,
            severity=severity,
            translation_key=issue_id,
            translation_placeholders=placeholders,
        )

    def _clear(self, *issue_ids: str) -> None:
        for issue_id in issue_ids:
            ir.async_delete_issue(self.hass, DOMAIN, f"{issue_id}_{self.config_entry.entry_id}")

    # -- update -------------------------------------------------------------
    def _schedule_next(self) -> None:
        """Every N minutes inside the active hours, nothing at night."""
        opts = self.config_entry.options
        self.update_interval = next_poll_delay(
            dt_util.now(),
            opts.get(CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES),
            opts.get(CONF_ACTIVE_FROM, DEFAULT_ACTIVE_FROM),
            opts.get(CONF_ACTIVE_TO, DEFAULT_ACTIVE_TO),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        # Set before fetching, so the next run is planned on failures too.
        self._schedule_next()
        try:
            data = await self.client.fetch_all(dt_util.now().date())
        except ManticaAuthError as err:
            n, limit = self.policy.counts["auth"] + 1, self.policy.LIMITS["auth"]
            if self.policy.record("auth") == ACTION_REAUTH:
                # Stops polling and asks the user for the password.
                raise ConfigEntryAuthFailed(str(err)) from err
            raise UpdateFailed(f"Login rejected ({n}/{limit}): {err}") from err
        except ManticaLayoutError as err:
            if self.policy.record("layout") == ACTION_ISSUE:
                self._issue(ISSUE_LAYOUT, ir.IssueSeverity.ERROR, details=str(err))
            raise UpdateFailed(f"Page layout not recognised: {err}") from err
        except ManticaConnectionError as err:
            if self.policy.record("conn") == ACTION_ISSUE:
                self._issue(
                    ISSUE_UNREACHABLE,
                    ir.IssueSeverity.WARNING,
                    details=str(err),
                    count=str(self.policy.counts["conn"]),
                )
            raise UpdateFailed(str(err)) from err

        self.policy.success()
        self._clear(ISSUE_LAYOUT, ISSUE_UNREACHABLE)
        if data["unknown_read_state"]:
            self._issue(
                ISSUE_ICON,
                ir.IssueSeverity.WARNING,
                details=", ".join(m["subject"] for m in data["unknown_read_state"][:3]),
            )
        else:
            self._clear(ISSUE_ICON)
        await self._update_messages(data)
        self._detect_new(data)
        return data

    # -- messages -------------------------------------------------------------
    async def _update_messages(self, data: dict[str, Any]) -> None:
        messages = data["messages"]
        inbox = {m["id"] for m in messages}
        before = (set(self._new_msgs), set(self._dismissed), set(self._bodies))
        for m in messages:
            if m["unread"] is True and m["id"] not in self._dismissed:
                self._new_msgs.add(m["id"])
        # Only the first inbox page is read; forget what fell off it.
        self._new_msgs &= inbox
        self._dismissed &= inbox
        self._bodies = {k: v for k, v in self._bodies.items() if k in inbox}

        fetched = 0
        for m in messages:  # newest first
            if m["id"] not in self._new_msgs or m["id"] in self._bodies:
                continue
            if fetched >= MAX_BODY_FETCHES:
                break
            fetched += 1
            try:
                html = await self.client.fetch_message_html(m["url"])
                self._bodies[m["id"]] = parser.parse_message_body(html)
            except (ManticaError, parser.LayoutError) as err:
                # The rest of the data is fine; try again on the next update.
                _LOGGER.warning("Could not read message %s: %s", m["id"], err)

        self._apply_message_state(data)
        if (set(self._new_msgs), set(self._dismissed), set(self._bodies)) != before:
            self._schedule_save()

    def _apply_message_state(self, data: dict[str, Any]) -> None:
        for m in data["messages"]:
            m["new"] = m["id"] in self._new_msgs
            m["body"] = self._bodies.get(m["id"])
        data["new_messages"] = [m for m in data["messages"] if m["new"]]

    async def async_mark_messages_read(self, ids: set[str] | None = None) -> None:
        """Clear the "new" flag in HA (all messages when ids is None)."""
        target = set(self._new_msgs) if ids is None else ids & self._new_msgs
        if not target:
            return
        self._new_msgs -= target
        self._dismissed |= target
        self._schedule_save()
        if self.data:
            self._apply_message_state(self.data)
            self.async_update_listeners()

    def _schedule_save(self) -> None:
        self._store.async_delay_save(
            lambda: {
                "id_format": ID_FORMAT,
                "grades": sorted(self._seen["grades"] or ()),
                "messages": sorted(self._seen["messages"] or ()),
                "events": sorted(self._seen["events"] or ()),
                "new_messages": sorted(self._new_msgs),
                "dismissed_messages": sorted(self._dismissed),
                "bodies": self._bodies,
            },
            10,
        )

    def _detect_new(self, data: dict[str, Any]) -> None:
        changed = False
        today = dt_util.now().date().isoformat()
        for kind, items, candidates, event, fields in (
            ("grades", data["grades"], data["grades"], EVENT_NEW_GRADE, GRADE_FIELDS),
            ("messages", data["messages"], data["messages"], EVENT_NEW_MESSAGE, MESSAGE_FIELDS),
            (
                "events",
                data["upcoming"],
                recently_added(data["upcoming"], today),
                EVENT_NEW_CALENDAR,
                CALENDAR_FIELDS,
            ),
        ):
            new, bulk = find_new(candidates, self._seen[kind])
            if bulk:
                _LOGGER.warning(
                    "%d new %s at once - sending one %s event instead of %d "
                    "separate ones (semester switch or site change?)",
                    len(new), kind, EVENT_BULK, len(new),
                )
                self.hass.bus.async_fire(
                    EVENT_BULK,
                    {
                        "type": kind,
                        "count": len(new),
                        "items": [{k: i[k] for k in fields} for i in new[:5]],
                    },
                )
            else:
                for item in new:
                    self.hass.bus.async_fire(event, {k: item[k] for k in fields})
            ids = {i["id"] for i in items}
            seen = self._seen[kind]
            if seen is None or not ids <= seen:
                self._seen[kind] = (seen or set()) | ids
                changed = True
        if changed:
            self._schedule_save()
