# ClickUp

You can import tasks from your ClickUp workspace using the `clickup`
service name.

ClickUp exposes a Personal API Token that grants access to all workspaces
your account can view.  Bugwarrior uses that token to page through the
*Get Filtered Team Tasks* endpoint and create/maintain corresponding
Taskwarrior tasks.

## Example Service

Here's a minimal ClickUp target:

.. config::

```
[my_clickup]
service        = clickup
api_token      = pk_0123456789ABCDEFGHIJKL          # Personal API Token
team_id        = 123456                             # Workspace / “Team” ID
```

The above example is enough to import tasks assigned to **you** that are
not archived.  You may also use any of the configuration options
explained in \:ref:`common_configuration_options` or documented in
`Service Features`\_ below.

.. note::
The *team\_id* value is the numeric **Team ID** shown in a task’s URL,
e.g. `https://app.clickup.com/t/123456/AB‑123` → *123456*.

## Service Features

Authentication Token
++++++++++++++++++++

Generate a **Personal API Token** from *Avatar → Settings → Apps → Personal
API Token* and paste it into `api_token` (or store it in a system
keyring—see \:ref:`password_options`).

Verify or Ignore SSL Certificates
+++++++++++++++++++++++++++++++++

If your ClickUp instance (or a proxy) presents an internal or
self‑signed certificate, disable verification:

.. config::
\:fragment: clickup

```
verify_ssl = False
```

Status Filter
+++++++++++++

By default the service pulls **open** tasks only.  To restrict the list
to specific statuses:

.. config::
\:fragment: clickup

```
statuses = to do,in progress,review
```

Tag Filter
++++++++++

Likewise you can filter by ClickUp *tags* (comma‑separated):

.. config::
\:fragment: clickup

```
tags = urgent,blocked
```

Include Only Assigned / Also Unassigned
++++++++++++++++++++++++++++++++++++++

Bugwarrior’s common option `only_if_assigned` defaults to *True* for
ClickUp, mirroring the Jira integration.  To turn it off and import all
workspace tasks you can access:

.. config::
\:fragment: clickup

```
only_if_assigned = False
```

If you keep `only_if_assigned = True` but still want unassigned tasks,
set the companion option:

.. config::
\:fragment: clickup

```
also_unassigned = True
```

Import Tags as Taskwarrior Tags
+++++++++++++++++++++++++++++++

ClickUp *tags* may be mirrored into Taskwarrior *tags* when
`import_labels_as_tags` is enabled:

.. config::
\:fragment: clickup

```
import_labels_as_tags = True
```

Use `label_template` to adjust formatting.  The default template
replaces spaces with underscores:

.. config::
\:fragment: clickup

```
label_template = {{label|replace(' ', '_')}}
```

Page Size
+++++++++

ClickUp’s API allows up to **100** tasks per page.  You can lower the
page size (e.g. to avoid timeouts on slow connections):

.. config::
\:fragment: clickup

```
page_size = 50
```

## Provided UDA Fields

.. udas:: bugwarrior.services.clickup.ClickupIssue
