import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

RQ_PATCH = "Controllers.DB.run_query"


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_conn():
    return MagicMock()

def make_timecard_df(pay_period="20250430", manager="mgr@crtct.org", approval=0):
    return pd.DataFrame([{
        "WorkEmail": "emp@crtct.org",
        "ManagerWorkEmail": manager,
        "PayPeriod": pay_period,
        "Approval": approval,
        "Acknowledged": 1,
    }])


# ── _format_pay_period ────────────────────────────────────────────────────────

class TestFormatPayPeriod:
    def test_valid_yyyymmdd_formats_correctly(self):
        """YYYYMMDD strings from the DB should become human-readable Month DD, YYYY strings."""
        from Jobs.notify_manager_on_acknowledge import _format_pay_period
        assert _format_pay_period("20250430") == "April 30, 2025"

    def test_invalid_value_returns_string_fallback(self):
        """If the value cannot be parsed as a date, it should come back as a plain string rather than raising."""
        from Jobs.notify_manager_on_acknowledge import _format_pay_period
        assert _format_pay_period("not-a-date") == "not-a-date"

    def test_integer_input_is_accepted(self):
        """Integer PayPeriod values (as stored in the DB) should be coerced to string before parsing."""
        from Jobs.notify_manager_on_acknowledge import _format_pay_period
        assert _format_pay_period(20250101) == "January 01, 2025"


# ── _build_email_body ─────────────────────────────────────────────────────────

class TestBuildEmailBody:
    def _pending(self, periods):
        """Build a minimal pending DataFrame with one row per period."""
        return pd.DataFrame([{"PayPeriod": p} for p in periods])

    def test_contains_employee_name(self):
        """The employee's full name must appear in the email body."""
        from Jobs.notify_manager_on_acknowledge import _build_email_body
        html = _build_email_body("Doe, John", "20250430", self._pending([]))
        assert "Doe, John" in html

    def test_contains_just_acknowledged_period(self):
        """The pay period that was just acknowledged must appear in the email as a formatted date."""
        from Jobs.notify_manager_on_acknowledge import _build_email_body
        html = _build_email_body("Doe, John", "20250430", self._pending([]))
        assert "April 30, 2025" in html

    def test_just_acknowledged_row_highlighted(self):
        """The just-acknowledged row should carry the green highlight style to distinguish it from pending rows."""
        from Jobs.notify_manager_on_acknowledge import _build_email_body
        html = _build_email_body("Doe, John", "20250430", self._pending([]))
        assert "Just Acknowledged" in html

    def test_pending_section_appears_when_other_periods_exist(self):
        """When there are other acknowledged-but-unapproved timecards, a pending section must appear in the email."""
        from Jobs.notify_manager_on_acknowledge import _build_email_body
        html = _build_email_body("Doe, John", "20250430", self._pending(["20250314"]))
        assert "Awaiting Approval" in html

    def test_pending_section_omitted_when_no_other_periods(self):
        """When there are no other pending timecards, the 'awaiting approval' section must be absent."""
        from Jobs.notify_manager_on_acknowledge import _build_email_body
        html = _build_email_body("Doe, John", "20250430", self._pending([]))
        assert "Awaiting Approval" not in html

    def test_all_pending_periods_appear_in_body(self):
        """Every pending pay period must be formatted and included in the email body."""
        from Jobs.notify_manager_on_acknowledge import _build_email_body
        html = _build_email_body("Doe, John", "20250430", self._pending(["20250314", "20250228"]))
        assert "March 14, 2025" in html
        assert "February 28, 2025" in html

    def test_contains_pars_link(self):
        """The PARS URL button must be present so the manager can navigate directly to the app."""
        from Jobs.notify_manager_on_acknowledge import _build_email_body, PARS_URL
        html = _build_email_body("Doe, John", "20250430", self._pending([]))
        assert PARS_URL in html


# ── _send_email ───────────────────────────────────────────────────────────────

class TestSendEmail:
    def test_returns_true_on_202(self):
        """A 202 Accepted response from the Graph API means the email was successfully queued."""
        from Jobs.notify_manager_on_acknowledge import _send_email
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        with patch("Jobs.notify_manager_on_acknowledge.requests.post", return_value=mock_resp):
            assert _send_email("token", "mgr@crtct.org", "Subject", "<p>body</p>") is True

    def test_returns_false_on_non_202(self):
        """Any status code other than 202 should be treated as a send failure."""
        from Jobs.notify_manager_on_acknowledge import _send_email
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("Jobs.notify_manager_on_acknowledge.requests.post", return_value=mock_resp):
            assert _send_email("token", "mgr@crtct.org", "Subject", "<p>body</p>") is False

    def test_sends_to_correct_address(self):
        """The Graph API call must target the provided recipient address."""
        from Jobs.notify_manager_on_acknowledge import _send_email
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        with patch("Jobs.notify_manager_on_acknowledge.requests.post", return_value=mock_resp) as mock_post:
            _send_email("token", "mgr@crtct.org", "Subject", "<p>body</p>")
        payload = mock_post.call_args[1]["json"]
        recipients = payload["message"]["toRecipients"]
        assert any(r["emailAddress"]["address"] == "mgr@crtct.org" for r in recipients)

    def test_uses_html_content_type(self):
        """The email body must be sent with contentType HTML so formatting renders correctly."""
        from Jobs.notify_manager_on_acknowledge import _send_email
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        with patch("Jobs.notify_manager_on_acknowledge.requests.post", return_value=mock_resp) as mock_post:
            _send_email("token", "mgr@crtct.org", "Subject", "<p>body</p>")
        body = mock_post.call_args[1]["json"]["message"]["body"]
        assert body["contentType"] == "HTML"


# ── notify_manager ────────────────────────────────────────────────────────────

class TestNotifyManager:
    def test_does_nothing_when_no_timecards(self):
        """If fn_GetTimeCards returns no rows for this employee, no email should be sent."""
        from Jobs.notify_manager_on_acknowledge import notify_manager
        with patch(RQ_PATCH, return_value=pd.DataFrame()), \
             patch("Jobs.notify_manager_on_acknowledge._get_graph_token") as mock_token, \
             patch("Jobs.notify_manager_on_acknowledge._send_email") as mock_send:
            notify_manager(make_conn(), "emp@crtct.org", "04/30/2025", "Doe, John")
        mock_token.assert_not_called()
        mock_send.assert_not_called()

    def test_does_nothing_when_query_returns_none(self):
        """If run_query returns None (DB error), notify_manager must exit silently without sending."""
        from Jobs.notify_manager_on_acknowledge import notify_manager
        with patch(RQ_PATCH, return_value=None), \
             patch("Jobs.notify_manager_on_acknowledge._send_email") as mock_send:
            notify_manager(make_conn(), "emp@crtct.org", "04/30/2025", "Doe, John")
        mock_send.assert_not_called()

    def test_sends_email_to_manager(self):
        """When a timecard is acknowledged, the email must go to the employee's manager."""
        from Jobs.notify_manager_on_acknowledge import notify_manager
        df = make_timecard_df(pay_period="20250430", manager="mgr@crtct.org")
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        with patch(RQ_PATCH, return_value=df), \
             patch("Jobs.notify_manager_on_acknowledge._get_graph_token", return_value="token"), \
             patch("Jobs.notify_manager_on_acknowledge.requests.post", return_value=mock_resp) as mock_post:
            notify_manager(make_conn(), "emp@crtct.org", "04/30/2025", "Doe, John")
        payload = mock_post.call_args[1]["json"]
        recipients = payload["message"]["toRecipients"]
        assert any(r["emailAddress"]["address"] == "mgr@crtct.org" for r in recipients)

    def test_converts_mmddyyyy_pay_period_to_yyyymmdd(self):
        """The MM/DD/YYYY pay period from the UI must be converted to YYYYMMDD before comparing against DB records."""
        from Jobs.notify_manager_on_acknowledge import notify_manager
        # Row has PayPeriod=20250430; passing 04/30/2025 should identify it as "just acknowledged"
        df = make_timecard_df(pay_period="20250430")
        with patch(RQ_PATCH, return_value=df), \
             patch("Jobs.notify_manager_on_acknowledge._get_graph_token", return_value="token"), \
             patch("Jobs.notify_manager_on_acknowledge._send_email") as mock_send:
            notify_manager(make_conn(), "emp@crtct.org", "04/30/2025", "Doe, John")
        mock_send.assert_called_once()

    def test_subject_contains_employee_name_and_period(self):
        """The email subject must include both the employee's full name and the formatted pay period."""
        from Jobs.notify_manager_on_acknowledge import notify_manager
        df = make_timecard_df(pay_period="20250430")
        captured = {}
        def fake_send(token, to, subject, body):
            captured["subject"] = subject
            return True
        with patch(RQ_PATCH, return_value=df), \
             patch("Jobs.notify_manager_on_acknowledge._get_graph_token", return_value="token"), \
             patch("Jobs.notify_manager_on_acknowledge._send_email", side_effect=fake_send):
            notify_manager(make_conn(), "emp@crtct.org", "04/30/2025", "Doe, John")
        assert "Doe, John" in captured["subject"]
        assert "April 30, 2025" in captured["subject"]

    def test_handles_exception_silently(self):
        """Any unexpected exception inside notify_manager must be caught — it must never crash the caller."""
        from Jobs.notify_manager_on_acknowledge import notify_manager
        with patch(RQ_PATCH, side_effect=Exception("unexpected DB failure")):
            notify_manager(make_conn(), "emp@crtct.org", "04/30/2025", "Doe, John")


# ── getFundAllocations ────────────────────────────────────────────────────────

class TestGetFundAllocations:
    PATCH = "Controllers.timecardAllocationController.run_query"

    def test_returns_list_of_dicts_with_fund_and_percentage(self):
        """getFundAllocations should return a list of {FundCode, Percentage} dicts for use in the tooltip."""
        from Controllers.timecardAllocationController import getFundAllocations
        df = pd.DataFrame([{"FundCode": "699", "Percentage": 100}])
        with patch(self.PATCH, return_value=df):
            result = getFundAllocations(MagicMock(), "emp@crtct.org")
        assert result == [{"FundCode": "699", "Percentage": 100}]

    def test_returns_empty_list_when_no_rows(self):
        """An empty DataFrame from ADUsers should return [] rather than raising."""
        from Controllers.timecardAllocationController import getFundAllocations
        with patch(self.PATCH, return_value=pd.DataFrame()):
            result = getFundAllocations(MagicMock(), "emp@crtct.org")
        assert result == []

    def test_returns_empty_list_when_query_returns_none(self):
        """If run_query returns None (DB error), getFundAllocations must return [] and not raise."""
        from Controllers.timecardAllocationController import getFundAllocations
        with patch(self.PATCH, return_value=None):
            result = getFundAllocations(MagicMock(), "emp@crtct.org")
        assert result == []

    def test_passes_email_as_param(self):
        """The work email must be forwarded as the query parameter so results are filtered to the correct employee."""
        from Controllers.timecardAllocationController import getFundAllocations
        with patch(self.PATCH, return_value=pd.DataFrame()) as mock_rq:
            getFundAllocations(MagicMock(), "specific@crtct.org")
        assert "specific@crtct.org" in mock_rq.call_args[0][2]

    def test_multiple_fund_codes_returned(self):
        """An employee split across multiple fund codes must produce one dict per code."""
        from Controllers.timecardAllocationController import getFundAllocations
        df = pd.DataFrame([
            {"FundCode": "699", "Percentage": 60},
            {"FundCode": "700", "Percentage": 40},
        ])
        with patch(self.PATCH, return_value=df):
            result = getFundAllocations(MagicMock(), "emp@crtct.org")
        assert len(result) == 2
        codes = {r["FundCode"] for r in result}
        assert codes == {"699", "700"}


# ── changeTimecardState — ApprovedBy preservation ─────────────────────────────

class TestChangeTimecardStateApprovedBy:
    PATCH = "Controllers.timecardAllocationController.run_query"

    def _side(self, prev_approval=0, prev_acknowledged=0):
        """Return a side_effect that serves the current-state SELECT then accepts the UPDATE."""
        state_df = pd.DataFrame([{"Approval": prev_approval, "Acknowledged": prev_acknowledged}])
        calls = {"n": 0}
        def side_effect(conn, query, params=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return state_df
            return None
        return side_effect

    def test_approved_by_param_is_none_when_approval_unchanged(self):
        """When the approval state does not change, the ApprovedBy CASE WHEN guard parameter must be None
        so the existing ApprovedBy value is preserved and not overwritten by the acknowledging employee."""
        from Controllers.timecardAllocationController import changeTimecardState
        with patch(self.PATCH, side_effect=self._side(prev_approval=1, prev_acknowledged=0)) as mock_rq:
            changeTimecardState("EMP001", "MGR01", "04/30/2025", MagicMock(), 1, 1)
        update_params = mock_rq.call_args[0][2]
        # new_approved_date (params[1]) drives the CASE WHEN; must be None when approval unchanged
        assert update_params[1] is None

    def test_approved_by_param_is_set_when_approval_changes(self):
        """When the approval state changes, the ApprovedBy CASE WHEN guard parameter must be non-None
        so the new approver code is written to the DB."""
        from Controllers.timecardAllocationController import changeTimecardState
        with patch(self.PATCH, side_effect=self._side(prev_approval=0, prev_acknowledged=0)) as mock_rq:
            changeTimecardState("EMP001", "MGR01", "04/30/2025", MagicMock(), 1, 0)
        update_params = mock_rq.call_args[0][2]
        assert update_params[1] is not None
        assert update_params[2] == "MGR01"

    def test_acknowledged_date_param_is_none_when_acknowledged_unchanged(self):
        """When the acknowledged state does not change, the AcknowledgedDate guard must be None
        so the original AcknowledgedDate is preserved."""
        from Controllers.timecardAllocationController import changeTimecardState
        with patch(self.PATCH, side_effect=self._side(prev_approval=0, prev_acknowledged=1)) as mock_rq:
            changeTimecardState("EMP001", "MGR01", "04/30/2025", MagicMock(), 0, 1)
        update_params = mock_rq.call_args[0][2]
        # new_acknowledged_date is params[6]; must be None when acknowledged unchanged
        assert update_params[6] is None

    def test_acknowledged_date_param_is_set_when_acknowledged_changes(self):
        """When the acknowledged state flips, the AcknowledgedDate guard must be non-None
        so the new date is stamped."""
        from Controllers.timecardAllocationController import changeTimecardState
        with patch(self.PATCH, side_effect=self._side(prev_approval=0, prev_acknowledged=0)) as mock_rq:
            changeTimecardState("EMP001", "MGR01", "04/30/2025", MagicMock(), 0, 1)
        update_params = mock_rq.call_args[0][2]
        assert update_params[6] is not None
