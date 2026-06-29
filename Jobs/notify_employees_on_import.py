import os
import toml
import requests
import msal
from datetime import datetime
from Controllers.DB import run_query

try:
    _secrets_path = os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")
    _secrets      = toml.load(_secrets_path)
    CLIENT_ID     = _secrets["AZURE_CLIENT_ID"]
    CLIENT_SECRET = _secrets["AZURE_CLIENT_SECRET"]
    TENANT_ID     = _secrets["AZURE_TENANT_ID"]
except (FileNotFoundError, KeyError):
    CLIENT_ID = CLIENT_SECRET = TENANT_ID = ""
SENDER_EMAIL  = "automation@crtct.org"
PARS_URL      = "https://apps.crtct.org:8056/"

GRAPH_SCOPES  = ["https://graph.microsoft.com/.default"]
AUTHORITY     = f"https://login.microsoftonline.com/{TENANT_ID}"


def _get_graph_token():
    app = msal.ConfidentialClientApplication(CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
    result = app.acquire_token_for_client(scopes=GRAPH_SCOPES)
    if "access_token" not in result:
        raise RuntimeError(f"Failed to acquire Graph token: {result.get('error_description')}")
    return result["access_token"]


def _format_pay_period(value):
    try:
        return datetime.strptime(str(value), "%Y%m%d").strftime("%B %d, %Y")
    except Exception:
        return str(value)


def _build_email_body(pay_period):
    formatted = _format_pay_period(pay_period)
    return f"""
        <p>Hello,</p>
        <p>A new pay period has been uploaded to PARS:</p>
        <table style="border-collapse:collapse; width:100%; font-family:Arial, sans-serif; font-size:14px; margin-bottom:20px;">
            <thead>
                <tr style="background-color:#4472C4; color:white;">
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Pay Period</th>
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Action Required</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="padding:8px; border:1px solid #ddd;">{formatted}</td>
                    <td style="padding:8px; border:1px solid #ddd; color:#e65c00; font-weight:bold;">Allocations Needed</td>
                </tr>
            </tbody>
        </table>
        <p>Please log in to PARS and complete your fund allocations for this pay period.</p>
        <p>
            <a href="{PARS_URL}" style="background-color:#4472C4; color:white; padding:10px 20px; text-decoration:none; border-radius:4px;">
                Go to PARS
            </a>
        </p>
        <br>
        <p style="color:#888; font-size:12px;">This is an automated notification from PARS.</p>
    """


def _send_email(token, to_address, subject, body):
    url = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body},
            "toRecipients": [{"emailAddress": {"address": to_address}}],
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.status_code == 202


def notify_employees_on_import(conn, pay_period):
    """
    Called after a successful timecard import.
    Emails every employee who has a Time_Card for the given pay period.
    pay_period must be in YYYYMMDD format.
    """
    try:
        df = run_query(conn, """
            SELECT DISTINCT e.WorkEmail
            FROM dbo.vw_EmployeeInformation e
            INNER JOIN dbo.Time_Card tc ON tc.EmployeeCode = e.EmployeeCode
            WHERE tc.PayPeriod = ?
              AND e.WorkEmail IS NOT NULL
        """, [pay_period])

        if df is None or df.empty:
            return

        token  = _get_graph_token()
        subject = f"PARS — New Pay Period Available: {_format_pay_period(pay_period)}"
        body    = _build_email_body(pay_period)

        for email in df["WorkEmail"].tolist():
            _send_email(token, email, subject, body)

    except Exception:
        pass
