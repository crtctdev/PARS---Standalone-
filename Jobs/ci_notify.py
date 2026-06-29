import os
from Jobs.notify_manager_on_acknowledge import _get_graph_token, _send_email

if not all([os.environ.get("AZURE_CLIENT_ID"), os.environ.get("AZURE_CLIENT_SECRET"), os.environ.get("AZURE_TENANT_ID")]):
    print("Skipping CI notification — Azure secrets not configured.")
    raise SystemExit(0)

status = os.environ.get("CI_STATUS", "unknown")
passed = status == "success"

subject = "PARS CI passed" if passed else "PARS CI FAILED"
body = (
    "<p>All tests passed on the <strong>Main</strong> branch.</p>"
    if passed else
    "<p>One or more tests <strong>failed</strong> on the <strong>Main</strong> branch. "
    "Check the <a href='https://github.com/crtctdev/PARS---Standalone-/actions'>Actions tab</a> for details.</p>"
)

token = _get_graph_token()
_send_email(token, "automation@crtct.org", subject, body)
print(f"CI notification sent: {subject}")
