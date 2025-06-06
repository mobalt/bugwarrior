"""
ClickUp service integration for **bugwarrior**
============================================

This file follows the same **Config → Issue → Service** pattern used by the
built‑in services (GitHub, Jira, Trello, etc.).  Drop it into
`bugwarrior/services/clickup.py` (or an import‑compatible location) and add a
`[my_clickup]` section in *~/.bugwarriorrc* like so:

```ini
[my_clickup]
service        = clickup
api_token      = pk_your_clickup_token
team_id        = 123456               # Workspace / Team ID
only_if_assigned = true               # ← common bugwarrior option
verify_ssl       = true
statuses         = to do,in progress  # optional filters
import_labels_as_tags = true          # turn ClickUp tags into Taskwarrior tags
```

The code intentionally mirrors the stylistic conventions of the other
integrations so maintainers can review it quickly.
"""
from __future__ import annotations

import datetime as _dt
import logging
import typing

import requests

from bugwarrior import config
from bugwarrior.services import Issue, Service, Client

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Configuration schema
# ---------------------------------------------------------------------------


class ClickupConfig(config.ServiceConfig):
    """Validate the *clickup* section of bugwarriorrc."""

    service: typing.Literal["clickup"]
    api_token: str
    team_id: typing.Union[int, str]

    verify_ssl: typing.Union[bool, config.ExpandedPath] = True
    page_size: int = 100  # ClickUp max page size

    statuses: config.ConfigList = config.ConfigList([])  # status filter
    tags: config.ConfigList = config.ConfigList([])      # tag filter

    import_labels_as_tags: bool = False  # ClickUp calls them *tags*
    label_template: str = "{{label|replace(' ', '_')}}"

    # XXX Override common option: default to *only* my tasks, like Jira
    only_if_assigned: bool = True


# ---------------------------------------------------------------------------
# 2. Issue model – translates ClickUp JSON → Taskwarrior fields
# ---------------------------------------------------------------------------


class ClickupIssue(Issue):
    """A single ClickUp task mapped to Taskwarrior."""

    ID = "clickupid"
    URL = "clickupurl"
    STATUS = "clickupstatus"
    PRIORITY = "clickuppriority"
    SPACE = "clickupspace"
    FOLDER = "clickupfolder"
    LIST = "clickuplist"

    UDAS = {
        ID: {"type": "string", "label": "ClickUp Task ID"},
        URL: {"type": "string", "label": "ClickUp URL"},
        STATUS: {"type": "string", "label": "ClickUp Status"},
        PRIORITY: {"type": "string", "label": "ClickUp Priority"},
        SPACE: {"type": "string", "label": "ClickUp Space"},
        FOLDER: {"type": "string", "label": "ClickUp Folder"},
        LIST: {"type": "string", "label": "ClickUp List"},
    }

    UNIQUE_KEY = (ID,)  # prevents duplicates

    PRIORITY_MAP = {
        "urgent": "H",
        "high": "H",
        "normal": "M",
        "low": "L",
    }

    # ------------- Conversion helpers ----------------------------------
    def to_taskwarrior(self):
        due = self._parse_millis(self.record.get("due_date"))
        created = self._parse_millis(self.record.get("date_created"))
        updated = self._parse_millis(self.record.get("date_updated"))

        return {
            "project": self._project(),
            "priority": self.get_priority(),
            "tags": self.get_tags(),
            "due": due,
            "entry": created,
            "modified": updated,

            self.ID: self.record["id"],
            self.URL: self.record["url"],
            self.STATUS: self._status().lower(),
            self.PRIORITY: (self.record.get("priority") or {}).get("priority"),
            self.SPACE: self._container_name("space"),
            self.FOLDER: self._container_name("folder"),
            self.LIST: self._container_name("list"),
        }

    def get_default_description(self):
        return self.build_default_description(
            title=self.record.get("name"),
            url=self.record.get("url"),
            number=int(self.record["id"]),
            cls="task",
        )

    # ------------- Helpers ----------------------------------------------
    def _parse_millis(self, millis) -> typing.Optional[_dt.datetime]:
        if not millis:
            return None
        try:
            return _dt.datetime.fromtimestamp(int(millis) / 1000, _dt.timezone.utc).replace(microsecond=0)
        except Exception:
            return None

    def _status(self):
        return (self.record.get("status") or {}).get("status", "open")

    def _project(self):
        parts = [
            self._container_name("space"),
            self._container_name("folder"),
            self._container_name("list"),
        ]
        return "/".join(filter(None, parts)) or "ClickUp"

    def _container_name(self, key):
        container = self.record.get(key)
        return container.get("name") if isinstance(container, dict) else ""

    def get_priority(self):
        return self.PRIORITY_MAP.get(
            (self.record.get("priority") or {}).get("priority", "normal").lower(),
            self.config.default_priority,
        )

    def get_tags(self):
        labels = [label["name"] for label in self.record.get("tags", [])]
        return self.get_tags_from_labels(labels)


# ---------------------------------------------------------------------------
# 3. Client – thin wrapper around ClickUp REST
# ---------------------------------------------------------------------------


class ClickupClient(Client):
    """Minimal helper for ClickUp REST API v2."""

    BASE = "https://api.clickup.com/api/v2"

    def __init__(self, api_token: str, verify_ssl: typing.Union[bool, str]):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": api_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        if not verify_ssl:
            requests.packages.urllib3.disable_warnings()
            self.session.verify = False

    def json_get(self, path: str, **params):
        resp = self.session.get(f"{self.BASE}{path}", params=params, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"ClickUp API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    # ---------------- Helper endpoints ----------------
    def current_user_id(self):
        return str(self.json_get("/user")["user"]["id"])

    def team_tasks(self, team_id: typing.Union[int, str], **params):
        """Yield tasks from *Get Filtered Team Tasks* endpoint, auto‑paging."""
        page = 0
        while True:
            payload = {"page": page, **params}
            data = self.json_get(f"/team/{team_id}/task", **payload)
            tasks = data.get("tasks", [])
            if not tasks:
                break
            yield from tasks
            page += 1


# ---------------------------------------------------------------------------
# 4. Service glue – wires everything into bugwarrior
# ---------------------------------------------------------------------------


class ClickupService(Service, ClickupClient):
    """bugwarrior *service* implementation for ClickUp."""

    ISSUE_CLASS = ClickupIssue
    CONFIG_SCHEMA = ClickupConfig

    def __init__(self, *args, **kwargs):
        # Initialise Service base first …
        Service.__init__(self, *args, **kwargs)
        # … then Client with API details
        ClickupClient.__init__(
            self,
            api_token=self.get_password("api_token", "clickup"),
            verify_ssl=self.config.verify_ssl,
        )

        # Cache the authorised user's ClickUp ID for filtering
        self._user_id = None

    # ------------------------ keyring helper ----------------------------
    @staticmethod
    def get_keyring_service(cfg):  # pylint: disable=unused-argument
        return "clickup://api_token"

    # ------------------------ main entry -------------------------------
    def issues(self):  # noqa: D401 – expected override name
        """Generator yielding ClickupIssue objects."""
        user_id = self._get_user_id()
        status_filters = list(self.config.statuses)
        tag_filters = list(self.config.tags)

        common_params = {
            "archived": "false",
            "subtasks": "true",
            "page_size": self.config.page_size,
        }

        if self.config.only_if_assigned and user_id:
            common_params["assignees[]"] = user_id
        if status_filters:
            common_params["statuses[]"] = status_filters
        if tag_filters:
            common_params["tags[]"] = tag_filters

        for task in self.team_tasks(self.config.team_id, **common_params):
            # Respect only_if_assigned when the API filter isn't available (e.g. also_unassigned)
            if self._skip_due_to_assignment(task, user_id):
                continue
            yield self.get_issue_for_record(task)

    # ----------------- helper methods ---------------------------------
    def _get_user_id(self):
        if self._user_id is None:
            try:
                self._user_id = self.current_user_id()
                log.debug("ClickUp user id resolved as %s", self._user_id)
            except Exception as exc:  # pylint: disable=broad-except
                log.warning("Failed to resolve ClickUp user id: %s", exc)
        return self._user_id

    def _skip_due_to_assignment(self, task, user_id):
        if not self.config.only_if_assigned:
            return False
        assignees = [str(a.get("id")) for a in task.get("assignees", [])]
        if user_id in assignees:
            return False
        if self.config.also_unassigned and not assignees:
            return False
        return True
