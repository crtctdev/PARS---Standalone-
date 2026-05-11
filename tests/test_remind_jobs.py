import pytest
import pandas as pd
from unittest.mock import patch, MagicMock


def make_cursor(rows, columns):
    cursor = MagicMock()
    cursor.description = [(col,) for col in columns]
    cursor.fetchall.return_value = rows
    return cursor


def make_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


# ── remind_unacknowledged ─────────────────────────────────────────────────────

class TestFormatPayPeriodUnacknowledged:
    def test_valid_yyyymmdd_formats_correctly(self):
        """YYYYMMDD integers from the DB should become human-readable Month DD, YYYY strings."""
        from Jobs.remind_unacknowledged import format_pay_period
        assert format_pay_period(20260430) == "April 30, 2026"

    def test_invalid_value_returns_string(self):
        """If PayPeriod cannot be parsed it should come back as a plain string rather than raising."""
        from Jobs.remind_unacknowledged import format_pay_period
        assert format_pay_period("bad") == "bad"


class TestBuildEmailBodyUnacknowledged:
    def test_contains_pay_period(self):
        """The formatted pay period date must appear in the email body."""
        from Jobs.remind_unacknowledged import build_email_body
        rows = [{"PayPeriod": 20260430, "Approval": 0, "TimeCardId": "TCARD001"}]
        html = build_email_body(rows)
        assert "April 30, 2026" in html

    def test_approved_yes_when_approval_truthy(self):
        """Approval=1 should render as 'Yes' in the email table."""
        from Jobs.remind_unacknowledged import build_email_body
        rows = [{"PayPeriod": 20260430, "Approval": 1, "TimeCardId": "TCARD001"}]
        assert "Yes" in build_email_body(rows)

    def test_approved_no_when_approval_falsy(self):
        """Approval=0 should render as 'No' in the email table."""
        from Jobs.remind_unacknowledged import build_email_body
        rows = [{"PayPeriod": 20260430, "Approval": 0, "TimeCardId": "TCARD001"}]
        assert "No" in build_email_body(rows)

    def test_contains_pars_link(self):
        """The PARS URL button must be present so employees can navigate directly to the app."""
        from Jobs.remind_unacknowledged import build_email_body, PARS_URL
        rows = [{"PayPeriod": 20260430, "Approval": 0, "TimeCardId": "TCARD001"}]
        assert PARS_URL in build_email_body(rows)

    def test_multiple_rows_all_appear(self):
        """When an employee has multiple unacknowledged timecards, each pay period must appear in the email."""
        from Jobs.remind_unacknowledged import build_email_body
        rows = [
            {"PayPeriod": 20260430, "Approval": 0, "TimeCardId": "TCARD001"},
            {"PayPeriod": 20260314, "Approval": 0, "TimeCardId": "TCARD002"},
        ]
        html = build_email_body(rows)
        assert "April 30, 2026" in html
        assert "March 14, 2026" in html


class TestGetUnacknowledged:
    def test_returns_dataframe_with_correct_columns(self):
        """get_unacknowledged should return a DataFrame shaped by the cursor's column descriptions."""
        from Jobs.remind_unacknowledged import get_unacknowledged
        columns = ["TimeCardId", "PayPeriod", "Approval", "ApprovedDate", "Acknowledged", "WorkEmail", "ManagerWorkEmail"]
        cursor = make_cursor([("TCARD001", 20260430, 0, None, None, "emp@crtct.org", "mgr@crtct.org")], columns)
        df = get_unacknowledged(make_conn(cursor))
        assert list(df.columns) == columns
        assert len(df) == 1

    def test_returns_empty_dataframe_when_no_rows(self):
        """An empty result from the DB should come back as an empty DataFrame, not raise."""
        from Jobs.remind_unacknowledged import get_unacknowledged
        columns = ["TimeCardId", "PayPeriod", "Approval", "ApprovedDate", "Acknowledged", "WorkEmail", "ManagerWorkEmail"]
        cursor = make_cursor([], columns)
        df = get_unacknowledged(make_conn(cursor))
        assert df.empty


class TestSendEmailUnacknowledged:
    def test_returns_true_on_202(self):
        """A 202 Accepted response from Graph means the email was queued successfully."""
        from Jobs.remind_unacknowledged import send_email
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        with patch("Jobs.remind_unacknowledged.requests.post", return_value=mock_resp):
            result = send_email("token", "emp@crtct.org", [{"PayPeriod": 20260430, "Approval": 0, "TimeCardId": "T1"}])
        assert result is True

    def test_returns_false_on_non_202(self):
        """Any response other than 202 should be treated as a failure."""
        from Jobs.remind_unacknowledged import send_email
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        with patch("Jobs.remind_unacknowledged.requests.post", return_value=mock_resp):
            result = send_email("token", "emp@crtct.org", [{"PayPeriod": 20260430, "Approval": 0, "TimeCardId": "T1"}])
        assert result is False


class TestMainUnacknowledged:
    def test_no_email_sent_when_no_unacknowledged(self, capsys):
        """When every timecard is acknowledged, no Graph call should be made and the output says so."""
        from Jobs.remind_unacknowledged import main
        columns = ["TimeCardId", "PayPeriod", "Approval", "ApprovedDate", "Acknowledged", "WorkEmail", "ManagerWorkEmail"]
        cursor = make_cursor([], columns)
        with patch("Jobs.remind_unacknowledged.pyodbc.connect", return_value=make_conn(cursor)):
            main()
        assert "No unacknowledged timecards found" in capsys.readouterr().out

    def test_sends_one_email_per_employee(self, capsys):
        """Each unique WorkEmail should receive exactly one email containing all their timecards."""
        from Jobs.remind_unacknowledged import main
        columns = ["TimeCardId", "PayPeriod", "Approval", "ApprovedDate", "Acknowledged", "WorkEmail", "ManagerWorkEmail"]
        rows = [
            ("TCARD001", 20260430, 0, None, None, "emp@crtct.org", "mgr@crtct.org"),
            ("TCARD002", 20260314, 0, None, None, "emp@crtct.org", "mgr@crtct.org"),
        ]
        cursor = make_cursor(rows, columns)
        mock_resp = MagicMock()
        mock_resp.status_code = 202

        with patch("Jobs.remind_unacknowledged.pyodbc.connect", return_value=make_conn(cursor)), \
             patch("Jobs.remind_unacknowledged.get_graph_token", return_value="token"), \
             patch("Jobs.remind_unacknowledged.requests.post", return_value=mock_resp) as mock_post:
            main()

        assert mock_post.call_count == 1


# ── remind_managers ───────────────────────────────────────────────────────────

class TestFormatPayPeriodManagers:
    def test_valid_yyyymmdd_formats_correctly(self):
        """YYYYMMDD integers from the DB should become human-readable Month DD, YYYY strings."""
        from Jobs.remind_managers import format_pay_period
        assert format_pay_period(20260430) == "April 30, 2026"

    def test_invalid_value_returns_string(self):
        """If PayPeriod cannot be parsed it should come back as a plain string rather than raising."""
        from Jobs.remind_managers import format_pay_period
        assert format_pay_period("bad") == "bad"


class TestBuildEmailBodyManagers:
    def test_contains_employee_email(self):
        """The employee's email must appear in the manager's email body."""
        from Jobs.remind_managers import build_email_body
        rows = [{"EmployeeEmail": "emp@crtct.org", "PayPeriod": 20260430}]
        assert "emp@crtct.org" in build_email_body(rows)

    def test_contains_pay_period(self):
        """The formatted pay period must appear in the manager's email body."""
        from Jobs.remind_managers import build_email_body
        rows = [{"EmployeeEmail": "emp@crtct.org", "PayPeriod": 20260430}]
        assert "April 30, 2026" in build_email_body(rows)

    def test_contains_pars_link(self):
        """The PARS URL button must be present so managers can navigate directly to the app."""
        from Jobs.remind_managers import build_email_body, PARS_URL
        rows = [{"EmployeeEmail": "emp@crtct.org", "PayPeriod": 20260430}]
        assert PARS_URL in build_email_body(rows)

    def test_multiple_employees_all_appear(self):
        """When a manager has multiple employees pending, each employee must appear in the email."""
        from Jobs.remind_managers import build_email_body
        rows = [
            {"EmployeeEmail": "emp1@crtct.org", "PayPeriod": 20260430},
            {"EmployeeEmail": "emp2@crtct.org", "PayPeriod": 20260430},
        ]
        html = build_email_body(rows)
        assert "emp1@crtct.org" in html
        assert "emp2@crtct.org" in html


class TestGetUnapproved:
    def test_returns_dataframe_with_correct_columns(self):
        """get_unapproved should return a DataFrame shaped by the cursor's column descriptions."""
        from Jobs.remind_managers import get_unapproved
        columns = ["ManagerWorkEmail", "EmployeeEmail", "PayPeriod", "Approval", "Acknowledged"]
        cursor = make_cursor([("mgr@crtct.org", "emp@crtct.org", 20260430, 0, 1)], columns)
        df = get_unapproved(make_conn(cursor))
        assert list(df.columns) == columns
        assert len(df) == 1

    def test_returns_empty_dataframe_when_no_rows(self):
        """An empty result should come back as an empty DataFrame, not raise."""
        from Jobs.remind_managers import get_unapproved
        columns = ["ManagerWorkEmail", "EmployeeEmail", "PayPeriod", "Approval", "Acknowledged"]
        cursor = make_cursor([], columns)
        df = get_unapproved(make_conn(cursor))
        assert df.empty


class TestSendEmailManagers:
    def test_returns_true_on_202(self):
        """A 202 Accepted response from Graph means the email was queued successfully."""
        from Jobs.remind_managers import send_email
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        with patch("Jobs.remind_managers.requests.post", return_value=mock_resp):
            result = send_email("token", "mgr@crtct.org", [{"EmployeeEmail": "emp@crtct.org", "PayPeriod": 20260430}])
        assert result is True

    def test_returns_false_on_non_202(self):
        """Any response other than 202 should be treated as a failure."""
        from Jobs.remind_managers import send_email
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("Jobs.remind_managers.requests.post", return_value=mock_resp):
            result = send_email("token", "mgr@crtct.org", [{"EmployeeEmail": "emp@crtct.org", "PayPeriod": 20260430}])
        assert result is False


class TestMainManagers:
    def test_no_email_sent_when_nothing_pending(self, capsys):
        """When all timecards are approved, no Graph call should be made and the output says so."""
        from Jobs.remind_managers import main
        columns = ["ManagerWorkEmail", "EmployeeEmail", "PayPeriod", "Approval", "Acknowledged"]
        cursor = make_cursor([], columns)
        with patch("Jobs.remind_managers.pyodbc.connect", return_value=make_conn(cursor)):
            main()
        assert "No unapproved timecards found" in capsys.readouterr().out

    def test_sends_one_email_per_manager(self, capsys):
        """Each unique ManagerWorkEmail should receive exactly one email covering all their employees."""
        from Jobs.remind_managers import main
        columns = ["ManagerWorkEmail", "EmployeeEmail", "PayPeriod", "Approval", "Acknowledged"]
        rows = [
            ("mgr@crtct.org", "emp1@crtct.org", 20260430, 0, 1),
            ("mgr@crtct.org", "emp2@crtct.org", 20260430, 0, 1),
        ]
        cursor = make_cursor(rows, columns)
        mock_resp = MagicMock()
        mock_resp.status_code = 202

        with patch("Jobs.remind_managers.pyodbc.connect", return_value=make_conn(cursor)), \
             patch("Jobs.remind_managers.get_graph_token", return_value="token"), \
             patch("Jobs.remind_managers.requests.post", return_value=mock_resp) as mock_post:
            main()

        assert mock_post.call_count == 1
