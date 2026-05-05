import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock, call
from datetime import datetime

PATCH = "Controllers.timecardAllocationController.run_query"


# ── Helpers ───────────────────────────────────────────────────────────────────

def empty_df():
    return pd.DataFrame()

def make_df(rows):
    """Build a minimal timecard DataFrame."""
    return pd.DataFrame(rows)

def make_conn():
    return MagicMock()


# ── getPayPeriods ─────────────────────────────────────────────────────────────

class TestGetPayPeriods:
    def test_formats_yyyymmdd_to_mmddyyyy(self):
        """PayPeriod values stored as YYYYMMDD in the DB should be returned as MM/DD/YYYY strings."""
        from Controllers.timecardAllocationController import getPayPeriods
        with patch(PATCH, return_value=pd.DataFrame({"PayPeriod": ["20250101", "20250201"]})):
            result = getPayPeriods(make_conn())
        assert result == ["01/01/2025", "02/01/2025"]

    def test_returns_empty_list_when_no_periods(self):
        """When Time_Card has no rows, getPayPeriods should return an empty list rather than raising."""
        from Controllers.timecardAllocationController import getPayPeriods
        with patch(PATCH, return_value=pd.DataFrame({"PayPeriod": pd.Series([], dtype=str)})):
            result = getPayPeriods(make_conn())
        assert result == []


# ── checkState ────────────────────────────────────────────────────────────────

class TestCheckState:
    def test_returns_zeros_when_no_timecard(self):
        """If no Time_Card row exists for the employee/period, both approval and acknowledged should default to 0."""
        from Controllers.timecardAllocationController import checkState
        with patch(PATCH, return_value=empty_df()):
            assert checkState("EMP001", "04/30/2025", make_conn()) == (0, 0)

    def test_returns_correct_approval_and_acknowledged(self):
        """When a Time_Card exists with Approval=1 and Acknowledged=1, both values should be returned."""
        from Controllers.timecardAllocationController import checkState
        df = pd.DataFrame({"Approval": [1], "Acknowledged": [1]})
        with patch(PATCH, return_value=df):
            assert checkState("EMP001", "04/30/2025", make_conn()) == (1, 1)

    def test_handles_null_values_as_zero(self):
        """NULL approval/acknowledged values in the DB should be treated as 0, not raise an error."""
        from Controllers.timecardAllocationController import checkState
        df = pd.DataFrame({"Approval": [None], "Acknowledged": [None]})
        with patch(PATCH, return_value=df):
            assert checkState("EMP001", "04/30/2025", make_conn()) == (0, 0)

    def test_builds_correct_timecardid(self):
        """The TimeCardID passed to the query must follow the TCARD{EmployeeCode}{YYYYMMDD} format."""
        from Controllers.timecardAllocationController import checkState
        with patch(PATCH, return_value=empty_df()) as mock_rq:
            checkState("EMP001", "04/30/2025", make_conn())
        params = mock_rq.call_args[0][2]
        assert params == ["TCARDEMP00120250430"]

    def test_pay_period_format_conversion(self):
        """MM/DD/YYYY pay period input must be converted to YYYYMMDD when building the TimeCardID."""
        from Controllers.timecardAllocationController import checkState
        with patch(PATCH, return_value=empty_df()) as mock_rq:
            checkState("EMP001", "12/31/2024", make_conn())
        params = mock_rq.call_args[0][2]
        assert params == ["TCARDEMP00120241231"]


# ── changeTimecardState ───────────────────────────────────────────────────────

class TestChangeTimecardState:
    def test_calls_update_with_correct_timecardid(self):
        """The UPDATE must target the exact TimeCardID built from employee code and pay period."""
        from Controllers.timecardAllocationController import changeTimecardState
        with patch(PATCH) as mock_rq:
            changeTimecardState("EMP001", "MGR01", "04/30/2025", make_conn(), 1, 0)
        params = mock_rq.call_args[0][2]
        assert "TCARDEXP00120250430" not in str(params)
        assert params[5] == "TCARDEMP00120250430"

    def test_sets_approval_and_acknowledged(self):
        """Approval, approver code, and acknowledged flag must all be passed in the correct parameter positions."""
        from Controllers.timecardAllocationController import changeTimecardState
        with patch(PATCH) as mock_rq:
            changeTimecardState("EMP001", "MGR01", "04/30/2025", make_conn(), 1, 1)
        params = mock_rq.call_args[0][2]
        assert params[0] == 1       # Approval
        assert params[3] == 1       # Acknowledged
        assert params[1] == "MGR01" # ApprovedBy


# ── getTasks ──────────────────────────────────────────────────────────────────

class TestGetTasks:
    def test_concatenates_code_and_description(self):
        """Tasks should be returned as 'Code:Description' strings for use in the UI selectbox."""
        from Controllers.timecardAllocationController import getTasks
        df = pd.DataFrame({"Code": ["A1", "B2"], "Description": ["Task A", "Task B"]})
        with patch(PATCH, return_value=df):
            result = getTasks(make_conn())
        assert result == ["A1:Task A", "B2:Task B"]

    def test_returns_empty_list_when_no_tasks(self):
        """When the Activities table is empty, getTasks should return an empty list without raising."""
        from Controllers.timecardAllocationController import getTasks
        df = pd.DataFrame({"Code": pd.Series([], dtype=str), "Description": pd.Series([], dtype=str)})
        with patch(PATCH, return_value=df):
            result = getTasks(make_conn())
        assert result == []


# ── getFundsByEmployee ────────────────────────────────────────────────────────

class TestGetFundsByEmployee:
    def test_concatenates_code_and_description(self):
        """Funds should be returned as 'FundCode:FundDescription' strings for use in the UI selectbox."""
        from Controllers.timecardAllocationController import getFundsByEmployee
        df = pd.DataFrame({"FundCode": ["F01"], "FundDescription": ["General Fund"]})
        with patch(PATCH, return_value=df):
            result = getFundsByEmployee(make_conn(), "EMP001")
        assert result == ["F01:General Fund"]

    def test_passes_employee_code_as_param(self):
        """The employee code must be forwarded as a query parameter so results are filtered to that employee."""
        from Controllers.timecardAllocationController import getFundsByEmployee
        df = pd.DataFrame({"FundCode": pd.Series([], dtype=str), "FundDescription": pd.Series([], dtype=str)})
        with patch(PATCH, return_value=df) as mock_rq:
            getFundsByEmployee(make_conn(), "EMP999")
        assert "EMP999" in mock_rq.call_args[0][2]


# ── deleteRecord ──────────────────────────────────────────────────────────────

class TestDeleteRecord:
    def test_calls_delete_with_like_pattern(self):
        """deleteRecord must use a LIKE %id% pattern to match the record ID rather than an exact equality check."""
        from Controllers.timecardAllocationController import deleteRecord
        with patch(PATCH) as mock_rq:
            deleteRecord(make_conn(), 42)
        params = mock_rq.call_args[0][2]
        assert params == ["%42%"]


# ── saveAllocations ───────────────────────────────────────────────────────────

class TestSaveAllocations:
    def _count_df(self, n=0):
        return pd.DataFrame({"count": [n]})

    def test_inserts_new_row_when_no_id(self):
        """Rows with no ID (NaN) should trigger an INSERT into dbo.Record with a generated ID."""
        from Controllers.timecardAllocationController import saveAllocations
        df = pd.DataFrame({"ID": [float("nan")], "Task": ["T1"], "Fund": ["F1"], "Hours": [4.0]})
        with patch(PATCH, return_value=self._count_df(10)) as mock_rq:
            saveAllocations(make_conn(), "SCH001", df)
        calls = [str(c) for c in mock_rq.call_args_list]
        assert any("INSERT" in c for c in calls)

    def test_updates_existing_row_when_id_present(self):
        """Rows with an existing ID should trigger an UPDATE rather than an INSERT."""
        from Controllers.timecardAllocationController import saveAllocations
        df = pd.DataFrame({"ID": [5.0], "Task": ["T1"], "Fund": ["F1"], "Hours": [4.0]})
        with patch(PATCH, return_value=self._count_df(10)) as mock_rq:
            saveAllocations(make_conn(), "SCH001", df)
        calls = [str(c) for c in mock_rq.call_args_list]
        assert any("UPDATE" in c for c in calls)

    def test_skips_rows_with_nan_hours(self):
        """Rows where Hours is NaN should be silently skipped — no INSERT or UPDATE should fire."""
        from Controllers.timecardAllocationController import saveAllocations
        df = pd.DataFrame({"ID": [float("nan")], "Task": ["T1"], "Fund": ["F1"], "Hours": [float("nan")]})
        with patch(PATCH, return_value=self._count_df(0)) as mock_rq:
            saveAllocations(make_conn(), "SCH001", df)
        # Only the initial COUNT query should fire
        assert mock_rq.call_count == 1

    def test_skips_fully_null_rows(self):
        """Rows where every column is None should be dropped before processing — no INSERT or UPDATE should fire."""
        from Controllers.timecardAllocationController import saveAllocations
        df = pd.DataFrame({"ID": [None], "Task": [None], "Fund": [None], "Hours": [None]})
        with patch(PATCH, return_value=self._count_df(0)) as mock_rq:
            saveAllocations(make_conn(), "SCH001", df)
        assert mock_rq.call_count == 1


# ── importTimeCards ───────────────────────────────────────────────────────────

class TestImportTimeCards:
    """
    run_query is called in a fixed order per import:
      1. vw_PayPeriods lookup
      2. Time_Card existence check (per employee)
      3. PayPeriodHours lookup (per employee-day group)
      4. EarnCode type lookup (per non-regular earn code)
      5. Schedule existence check + INSERT (per schedule entry)
      6. Backfill: PayPeriodHours + Schedule existence + INSERT per missing day
    """

    def _base_df(self, date="2025-04-30", ee="EMP001", hours=8.0, earn_code=""):
        return make_df([{
            "EECode": ee,
            "OutPunchTime": date,
            "EarnHours": hours,
            "EarnCode": earn_code,
        }])

    def test_uses_df_dates_when_no_period_match(self):
        """When vw_PayPeriods returns no match, max/min dates should come directly from OutPunchTime in the file."""
        from Controllers.timecardAllocationController import importTimeCards

        def side_effect(conn, query, params=None):
            if "vw_PayPeriods" in query:
                return empty_df()
            if "Time_Card" in query and "SELECT" in query:
                return pd.DataFrame({"TimeCardID": ["existing"]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Schedule" in query and "SELECT" in query:
                return empty_df()
            return None

        df = self._base_df()
        with patch(PATCH, side_effect=side_effect):
            _, _, _, max_date_str, min_date_str = importTimeCards(df, make_conn())

        assert max_date_str == "20250430"
        assert min_date_str == "20250430"

    def test_uses_existing_period_dates_when_matched(self):
        """When vw_PayPeriods returns a match, PayPeriod and PayPeriodStart from the DB should override the file dates."""
        from Controllers.timecardAllocationController import importTimeCards

        def side_effect(conn, query, params=None):
            if "vw_PayPeriods" in query:
                return pd.DataFrame({"PayPeriod": ["20250430"], "PayPeriodStart": ["20250421"]})
            if "Time_Card" in query and "SELECT" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Schedule" in query and "SELECT" in query:
                return empty_df()
            return None

        df = self._base_df()
        with patch(PATCH, side_effect=side_effect):
            _, _, _, max_date_str, min_date_str = importTimeCards(df, make_conn())

        assert max_date_str == "20250430"
        assert min_date_str == "20250421"

    def test_missing_employee_when_not_in_db(self):
        """An employee whose EECode has no matching EmployeeInformation row should appear in the missing list."""
        from Controllers.timecardAllocationController import importTimeCards

        def side_effect(conn, query, params=None):
            if "vw_PayPeriods" in query:
                return empty_df()
            if "Time_Card" in query and "SELECT" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "PayPeriodHours" in query:
                return empty_df()
            return None

        df = self._base_df()
        with patch(PATCH, side_effect=side_effect):
            _, missing, _, _, _ = importTimeCards(df, make_conn())

        assert "EMP001" in missing

    def test_missing_employee_when_hours_zero(self):
        """An employee with PayPeriodHours = 0 cannot have allocations calculated and should be flagged as missing."""
        from Controllers.timecardAllocationController import importTimeCards

        def side_effect(conn, query, params=None):
            if "vw_PayPeriods" in query:
                return empty_df()
            if "Time_Card" in query and "SELECT" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [0]})
            return None

        df = self._base_df()
        with patch(PATCH, side_effect=side_effect):
            _, missing, _, _, _ = importTimeCards(df, make_conn())

        assert "EMP001" in missing

    def test_new_schedule_record_increments_added_count(self):
        """Each Schedule INSERT for a new record (not already in the DB) should increment the records_added counter."""
        from Controllers.timecardAllocationController import importTimeCards

        def side_effect(conn, query, params=None):
            if "vw_PayPeriods" in query:
                return empty_df()
            if "Time_Card" in query and "SELECT" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "PaycomEarnCodes" in query:
                return pd.DataFrame({"Typedesc": ["Overtime"]})
            if "Schedule" in query and "SELECT" in query:
                return empty_df()
            return None

        df = self._base_df(earn_code="OT")
        with patch(PATCH, side_effect=side_effect):
            _, _, added, _, _ = importTimeCards(df, make_conn())

        assert added >= 1

    def test_existing_schedule_record_not_counted_as_added(self):
        """Schedule records that already exist in the DB should be added to existing_records and not count toward added."""
        from Controllers.timecardAllocationController import importTimeCards

        def side_effect(conn, query, params=None):
            if "vw_PayPeriods" in query:
                return empty_df()
            if "Time_Card" in query and "SELECT" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Schedule" in query and "SELECT" in query:
                return pd.DataFrame({"ScheduleID": ["existing"]})
            return None

        df = self._base_df()
        with patch(PATCH, side_effect=side_effect):
            existing, _, added, _, _ = importTimeCards(df, make_conn())

        assert added == 0
        assert len(existing) > 0

    def test_creates_timecard_when_not_existing(self):
        """When no Time_Card exists for an employee/period, an INSERT into dbo.Time_Card should be issued."""
        from Controllers.timecardAllocationController import importTimeCards

        calls = []

        def side_effect(conn, query, params=None):
            calls.append(query.strip()[:30])
            if "vw_PayPeriods" in query:
                return empty_df()
            if "Time_Card" in query and "SELECT" in query:
                return empty_df()  # card doesn't exist
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Schedule" in query and "SELECT" in query:
                return empty_df()
            return None

        df = self._base_df()
        with patch(PATCH, side_effect=side_effect):
            importTimeCards(df, make_conn())

        assert any("INSERT INTO dbo.Time_Card" in c for c in calls)

    def test_percentage_calculated_correctly_for_regular(self):
        """Percentage for a regular schedule entry should be (TotalHours / PayPeriodHours) * 100, rounded to 2dp."""
        from Controllers.timecardAllocationController import importTimeCards

        inserted_params = []

        def side_effect(conn, query, params=None):
            if "vw_PayPeriods" in query:
                return empty_df()
            if "Time_Card" in query and "SELECT" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Schedule" in query and "SELECT" in query:
                return empty_df()
            if "INSERT INTO dbo.Schedule" in query and params:
                inserted_params.append(params)
            return None

        # 4 hours out of 8 allowed = 50%
        df = self._base_df(hours=4.0)
        with patch(PATCH, side_effect=side_effect):
            importTimeCards(df, make_conn())

        pct_values = [p[5] for p in inserted_params if len(p) > 5]
        assert 50.0 in pct_values

    def test_pay_period_dates_are_weekdays_only(self):
        """Backfilled schedule entries should only be created for weekdays — Saturday and Sunday must be skipped."""
        from Controllers.timecardAllocationController import importTimeCards

        inserted_dates = []

        def side_effect(conn, query, params=None):
            if "vw_PayPeriods" in query:
                return empty_df()
            if "Time_Card" in query and "SELECT" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Schedule" in query and "SELECT" in query:
                return empty_df()
            if "INSERT INTO dbo.Schedule" in query and params:
                inserted_dates.append(params[2])
            return None

        # Monday 2025-04-28 as start so the 10-day window crosses a weekend
        df = self._base_df(date="2025-04-28")
        with patch(PATCH, side_effect=side_effect):
            importTimeCards(df, make_conn())

        for date_str in inserted_dates:
            dt = datetime.strptime(date_str, "%Y%m%d")
            assert dt.weekday() < 5, f"{date_str} is a weekend"


# ── importHistoryController ───────────────────────────────────────────────────

class TestImportHistoryController:
    def test_log_import_inserts_correct_fields(self):
        """All six fields — importer, pay period, start, records added, skipped, missing — must be passed in order."""
        from History.importHistoryController import logImport
        with patch("History.importHistoryController.run_query") as mock_rq:
            logImport(make_conn(), "user@test.com", "20250430", "20250421", 10, 2, ["EMP999"])
        params = mock_rq.call_args[0][2]
        assert params[0] == "user@test.com"
        assert params[1] == "20250430"
        assert params[2] == "20250421"
        assert params[3] == 10
        assert params[4] == 2
        assert params[5] == "EMP999"

    def test_log_import_joins_multiple_missing_employees(self):
        """Multiple missing employee codes should be stored as a single comma-joined string."""
        from History.importHistoryController import logImport
        with patch("History.importHistoryController.run_query") as mock_rq:
            logImport(make_conn(), "user@test.com", "20250430", "20250421", 5, 0, ["EMP001", "EMP002"])
        params = mock_rq.call_args[0][2]
        assert "EMP001" in params[5]
        assert "EMP002" in params[5]

    def test_log_import_uses_none_when_no_missing(self):
        """When no employees are missing, the MissingEmployees field should be stored as None rather than an empty string."""
        from History.importHistoryController import logImport
        with patch("History.importHistoryController.run_query") as mock_rq:
            logImport(make_conn(), "user@test.com", "20250430", "20250421", 5, 0, [])
        params = mock_rq.call_args[0][2]
        assert params[5] is None

    def test_get_import_history_orders_desc(self):
        """Import history should be returned newest-first (ORDER BY ImportedAt DESC) so the latest import is at the top."""
        from History.importHistoryController import getImportHistory
        with patch("History.importHistoryController.run_query") as mock_rq:
            getImportHistory(make_conn())
        query = mock_rq.call_args[0][1]
        assert "DESC" in query
