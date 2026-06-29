from Jobs.notify_manager_on_acknowledge import _get_graph_token, _send_email

token   = _get_graph_token()
subject = "PARS CI passed"
body    = "<p>All tests passed on the <strong>Main</strong> branch.</p>"
_send_email(token, "automation@crtct.org", subject, body)
print("CI success notification sent.")
