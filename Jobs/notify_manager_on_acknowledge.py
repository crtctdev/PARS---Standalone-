import os
import toml
import requests
import msal
import pandas as pd
from datetime import datetime

try:
    _secrets_path = os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")
    _s            = toml.load(_secrets_path)
    CLIENT_ID     = _s["AZURE_CLIENT_ID"]
    CLIENT_SECRET = _s["AZURE_CLIENT_SECRET"]
    TENANT_ID     = _s["AZURE_TENANT_ID"]
except (FileNotFoundError, KeyError):
    CLIENT_ID     = os.environ.get("AZURE_CLIENT_ID", "")
    CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
    TENANT_ID     = os.environ.get("AZURE_TENANT_ID", "")
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


def _build_email_body(employee_full_name, just_acknowledged_period, pending_df):
    just_row = f"""
        <tr style="background-color:#eaf7ea;">
            <td style="padding:8px; border:1px solid #ddd;">{_format_pay_period(just_acknowledged_period)}</td>
            <td style="padding:8px; border:1px solid #ddd; color:#2e7d32; font-weight:bold;">Just Acknowledged</td>
        </tr>
    """

    pending_rows_html = "".join(
        f"""<tr>
            <td style="padding:8px; border:1px solid #ddd;">{_format_pay_period(row["PayPeriod"])}</td>
            <td style="padding:8px; border:1px solid #ddd; color:#e65c00;">Awaiting Approval</td>
        </tr>"""
        for _, row in pending_df.iterrows()
    )

    pending_section = ""
    if pending_rows_html:
        pending_section = f"""
        <p>The following timecards for this employee have also been acknowledged and are still <strong>awaiting your approval</strong>:</p>
        <table style="border-collapse:collapse; width:100%; font-family:Arial, sans-serif; font-size:14px; margin-bottom:20px;">
            <thead>
                <tr style="background-color:#4472C4; color:white;">
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Pay Period</th>
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Status</th>
                </tr>
            </thead>
            <tbody>{pending_rows_html}</tbody>
        </table>
        """

    return f"""
        <p>Hello,</p>
        <p><strong>{employee_full_name}</strong> has acknowledged their timecard for the following pay period:</p>
        <table style="border-collapse:collapse; width:100%; font-family:Arial, sans-serif; font-size:14px; margin-bottom:20px;">
            <thead>
                <tr style="background-color:#4472C4; color:white;">
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Pay Period</th>
                    <th style="padding:8px; border:1px solid #ddd; text-align:left;">Status</th>
                </tr>
            </thead>
            <tbody>{just_row}</tbody>
        </table>
        {pending_section}
        <p>
            <a href="{PARS_URL}" style="background-color:#4472C4; color:white; padding:10px 20px; text-decoration:none; border-radius:4px;">
                Go to PARS to Approve
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


def notify_manager(conn, work_email, pay_period, employee_full_name):
    """
    Called immediately when an employee acknowledges a timecard.

    Emails the employee's manager with:
      - The timecard that was just acknowledged
      - Any other timecards for this employee that are acknowledged but still awaiting approval

    Args:
        conn: active DB connection
        work_email (str): the acknowledging employee's work email
        pay_period (str): pay period in MM/DD/YYYY format (as used in the UI)
        employee_full_name (str): display name used in the email subject/body
    """
    try:
        from Controllers.DB import run_query

        parts = pay_period.split("/")
        period = f"{parts[2]}{parts[0]}{parts[1]}"

        df = run_query(conn, """
            SELECT WorkEmail, ManagerWorkEmail, PayPeriod, Approval, Acknowledged
            FROM dbo.fn_GetTimeCards()
            WHERE LOWER(WorkEmail) = LOWER(?)
              AND Acknowledged = 1
              AND (Approval <> 1 OR Approval IS NULL)
        """, [work_email])

        if df is None or df.empty:
            return

        manager_email = df.iloc[0]["ManagerWorkEmail"]
        pending_df    = df[df["PayPeriod"].astype(str) != str(period)]

        subject = f"{employee_full_name} acknowledged their timecard — {_format_pay_period(period)}"
        body    = _build_email_body(employee_full_name, period, pending_df)

        token = _get_graph_token()
        success = _send_email(token, manager_email, subject, body)
        print(f"[notify_manager_on_acknowledge] {'SENT' if success else 'FAILED'} → {manager_email}")

    except Exception as e:
        print(f"[notify_manager_on_acknowledge] ERROR: {e}")
