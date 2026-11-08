"""Constants for the Mantica school diary integration."""
DOMAIN = "mantica"

# Options (Konfiguruj): how often and in which hours the portal is read.
CONF_SCAN_MINUTES = "scan_minutes"
CONF_ACTIVE_FROM = "active_from"
CONF_ACTIVE_TO = "active_to"
DEFAULT_SCAN_MINUTES = 60
DEFAULT_ACTIVE_FROM = 6
DEFAULT_ACTIVE_TO = 22
MIN_SCAN_MINUTES = 15
EVENT_NEW_GRADE = f"{DOMAIN}_new_grade"
EVENT_NEW_MESSAGE = f"{DOMAIN}_new_message"
EVENT_NEW_CALENDAR = f"{DOMAIN}_new_calendar_event"
EVENT_NEW_SUBSTITUTION = f"{DOMAIN}_new_substitution"
EVENT_NEW_REMARK = f"{DOMAIN}_new_remark"
EVENT_NEW_HOMEWORK = f"{DOMAIN}_new_homework"
EVENT_BULK = f"{DOMAIN}_bulk_update"

ISSUE_LAYOUT = "layout_changed"
ISSUE_UNREACHABLE = "site_unreachable"
ISSUE_ICON = "unknown_message_icon"
ISSUE_EXTRA = "extra_layout_changed"
