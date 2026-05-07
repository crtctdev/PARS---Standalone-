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
    Bulk queries are issued upfront per import:
      1. vw_PayPeriods lookup
      2. vw_EmployeeInformation bulk PayPeriodHours fetch
      3. PaycomEarnCodes bulk fetch
      4. Time_Card bulk existence check (by PayPeriod)
      5. Schedule bulk existence check (JOIN Time_Card by PayPeriod)
    TimeCard and Schedule INSERTs use cursor.executemany, not run_query.
    """

    def _base_df(self, date="2025-04-30", ee="EMP001", hours=8.0, earn_code=""):
        return make_df([{
            "EECode": ee,
            "InPunchTime": date,
            "EarnHours": hours,
            "EarnCode": earn_code,
        }])

    def _side(self, period_df=None, hours=8.0, existing_tc=True, existing_sched_ids=None, earn_codes=None):
        """Factory for standard side_effect functions."""
        def side_effect(conn, query, params=None):
            if "vw_PayPeriods" in query:
                return period_df if period_df is not None else empty_df()
            if "Time_Card WHERE PayPeriod" in query:
                return pd.DataFrame({"TimeCardID": ["TCARDEMP00120250430"]}) if existing_tc else empty_df()
            if "JOIN dbo.Time_Card" in query:
                ids = existing_sched_ids or []
                return pd.DataFrame({"ScheduleID": ids}) if ids else empty_df()
            if "vw_EmployeeInformation" in query:
                if hours is None:
                    return empty_df()
                return pd.DataFrame({"EmployeeCode": ["EMP001"], "PayPeriodHours": [hours]})
            if "PaycomEarnCodes" in query:
                codes = earn_codes or {}
                return pd.DataFrame({"Typecode": list(codes.keys()), "Typedesc": list(codes.values())})
            return None
        return side_effect

    def test_uses_df_dates_when_no_period_match(self):
        """When vw_PayPeriods returns no match, max/min dates should come directly from InPunchTime in the file."""
        from Controllers.timecardAllocationController import importTimeCards

        df = self._base_df()
        conn = make_conn()
        with patch(PATCH, side_effect=self._side()):
            _, _, _, max_date_str, min_date_str = importTimeCards(df, conn)

        assert max_date_str == "20250430"
        assert min_date_str == "20250430"

    def test_uses_existing_period_dates_when_matched(self):
        """When vw_PayPeriods returns a match, PayPeriod and PayPeriodStart from the DB should override the file dates."""
        from Controllers.timecardAllocationController import importTimeCards

        period = pd.DataFrame({"PayPeriod": ["20250430"], "PayPeriodStart": ["20250421"]})
        df = self._base_df()
        conn = make_conn()
        with patch(PATCH, side_effect=self._side(period_df=period)):
            _, _, _, max_date_str, min_date_str = importTimeCards(df, conn)

        assert max_date_str == "20250430"
        assert min_date_str == "20250421"

    def test_missing_employee_when_not_in_db(self):
        """An employee whose EECode has no matching EmployeeInformation row should appear in the missing list."""
        from Controllers.timecardAllocationController import importTimeCards

        df = self._base_df()
        conn = make_conn()
        with patch(PATCH, side_effect=self._side(hours=None)):
            _, missing, _, _, _ = importTimeCards(df, conn)

        assert "EMP001" in missing

    def test_missing_employee_when_hours_zero(self):
        """An employee with PayPeriodHours = 0 cannot have allocations calculated and should be flagged as missing."""
        from Controllers.timecardAllocationController import importTimeCards

        df = self._base_df()
        conn = make_conn()
        with patch(PATCH, side_effect=self._side(hours=0)):
            _, missing, _, _, _ = importTimeCards(df, conn)

        assert "EMP001" in missing

    def test_new_schedule_record_increments_added_count(self):
        """Each Schedule INSERT for a new record (not already in the DB) should increment the records_added counter."""
        from Controllers.timecardAllocationController import importTimeCards

        df = self._base_df(earn_code="OT")
        conn = make_conn()
        with patch(PATCH, side_effect=self._side(earn_codes={"OT": "Overtime"})):
            _, _, added, _, _ = importTimeCards(df, conn)

        assert added >= 1

    def test_existing_schedule_record_not_counted_as_added(self):
        """Schedule records that already exist in the DB should be added to existing_records and not count toward added."""
        from Controllers.timecardAllocationController import importTimeCards

        existing_id = "SCHEMP00120250430REG"
        df = self._base_df()
        conn = make_conn()
        with patch(PATCH, side_effect=self._side(existing_sched_ids=[existing_id])):
            existing, _, _, _, _ = importTimeCards(df, conn)

        assert existing_id in existing

    def test_creates_timecard_when_not_existing(self):
        """When no Time_Card exists for an employee/period, cursor.executemany should be called with a Time_Card INSERT."""
        from Controllers.timecardAllocationController import importTimeCards

        df = self._base_df()
        conn = make_conn()
        with patch(PATCH, side_effect=self._side(existing_tc=False)):
            importTimeCards(df, conn)

        calls = conn.cursor.return_value.executemany.call_args_list
        assert any("Time_Card" in str(c) for c in calls)

    def test_percentage_calculated_correctly_for_regular(self):
        """Percentage for a regular schedule entry should be (TotalHours / PayPeriodHours) * 100, rounded to 2dp."""
        from Controllers.timecardAllocationController import importTimeCards

        # 4 hours out of 8 allowed = 50%
        df = self._base_df(hours=4.0)
        conn = make_conn()
        with patch(PATCH, side_effect=self._side()):
            importTimeCards(df, conn)

        schedule_rows = []
        for c in conn.cursor.return_value.executemany.call_args_list:
            query, rows = c[0]
            if "Schedule" in query:
                schedule_rows.extend(rows)

        pct_values = [r[5] for r in schedule_rows]
        assert 50.0 in pct_values

    def test_pay_period_dates_are_weekdays_only(self):
        """Backfilled schedule entries should only be created for weekdays — Saturday and Sunday must be skipped."""
        from Controllers.timecardAllocationController import importTimeCards

        # Monday 2025-04-28 as start so the 10-day window crosses a weekend
        df = self._base_df(date="2025-04-28")
        conn = make_conn()
        with patch(PATCH, side_effect=self._side()):
            importTimeCards(df, conn)

        inserted_dates = []
        for c in conn.cursor.return_value.executemany.call_args_list:
            query, rows = c[0]
            if "Schedule" in query:
                inserted_dates.extend(r[2] for r in rows)

        for date_str in inserted_dates:
            dt = datetime.strptime(date_str, "%Y%m%d")
            assert dt.weekday() < 5, f"{date_str} is a weekend"


# ── autoAllocateSalariedEmployees ─────────────────────────────────────────────

class TestAutoAllocateSalariedEmployees:
    """
    Invariant: after any import, every active salaried employee (PayPeriodHours > 0)
    in EmployeeInformation must have a complete 10-business-day Regular schedule for
    the pay period. Employees already fully covered are skipped without any writes.
    """

    def _side(self, count=0, hours=8.0, card_exists=True, day_exists=False):
        """Common happy-path side_effect factory."""
        def side_effect(conn, query, params=None):
            if "COUNT(*) AS cnt" in query:
                return pd.DataFrame({"cnt": [count]})
            if "PayPeriodHours" in query:
                return empty_df() if hours is None else pd.DataFrame({"PayPeriodHours": [hours]})
            if "Time_Card WHERE TimeCardID" in query:
                return pd.DataFrame({"TimeCardID": ["x"]}) if card_exists else empty_df()
            if "INSERT INTO dbo.Time_Card" in query:
                return None
            if "Schedule WHERE ScheduleID" in query:
                return pd.DataFrame({"ScheduleID": ["x"]}) if day_exists else empty_df()
            if "INSERT INTO dbo.Schedule" in query:
                return None
            return None
        return side_effect

    def test_skips_employee_already_fully_allocated(self):
        """An employee with all 10 Regular days already in the DB must be skipped — no hours lookup or inserts should fire."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        with patch(PATCH, side_effect=self._side(count=10)) as mock_rq:
            result = autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])
        assert mock_rq.call_count == 1  # only the COUNT query
        assert result == []

    def test_allocates_ten_days_for_unallocated_employee(self):
        """An employee with no schedule for the period must receive exactly 10 Regular schedule inserts."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        inserted = []

        def side_effect(conn, query, params=None):
            if "COUNT(*) AS cnt" in query:
                return pd.DataFrame({"cnt": [0]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Time_Card WHERE TimeCardID" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "Schedule WHERE ScheduleID" in query:
                return empty_df()
            if "INSERT INTO dbo.Schedule" in query and params:
                inserted.append(params)
            return None

        with patch(PATCH, side_effect=side_effect):
            autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])

        assert len(inserted) == 10

    def test_employee_in_returned_list_after_allocation(self):
        """An employee who receives at least one new schedule day must appear in the returned list."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        with patch(PATCH, side_effect=self._side(count=0, hours=8.0)):
            result = autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])
        assert "EMP001" in result

    def test_fully_allocated_employee_not_in_returned_list(self):
        """An employee skipped due to full coverage must not appear in the returned list."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        with patch(PATCH, side_effect=self._side(count=10)):
            result = autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])
        assert "EMP001" not in result

    def test_skips_employee_not_in_employee_information(self):
        """An employee code with no EmployeeInformation row must be silently skipped with no schedule writes."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        with patch(PATCH, side_effect=self._side(count=0, hours=None)):
            result = autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["GHOST01"])
        assert result == []

    def test_skips_employee_with_zero_pay_period_hours(self):
        """An employee with PayPeriodHours = 0 has no valid allocation amount and must be skipped."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        with patch(PATCH, side_effect=self._side(count=0, hours=0)):
            result = autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])
        assert result == []

    def test_creates_timecard_when_not_existing(self):
        """When no Time_Card exists for the employee and pay period, an INSERT into dbo.Time_Card must be issued."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        queries = []

        def side_effect(conn, query, params=None):
            queries.append(query.strip())
            if "COUNT(*) AS cnt" in query:
                return pd.DataFrame({"cnt": [0]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Time_Card WHERE TimeCardID" in query:
                return empty_df()
            if "Schedule WHERE ScheduleID" in query:
                return empty_df()
            return None

        with patch(PATCH, side_effect=side_effect):
            autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])

        assert any("INSERT INTO dbo.Time_Card" in q for q in queries)

    def test_does_not_create_timecard_when_already_exists(self):
        """When a Time_Card already exists for the employee and pay period, no INSERT into dbo.Time_Card should fire."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        queries = []

        def side_effect(conn, query, params=None):
            queries.append(query.strip())
            if "COUNT(*) AS cnt" in query:
                return pd.DataFrame({"cnt": [0]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Time_Card WHERE TimeCardID" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "Schedule WHERE ScheduleID" in query:
                return empty_df()
            return None

        with patch(PATCH, side_effect=side_effect):
            autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])

        assert not any("INSERT INTO dbo.Time_Card" in q for q in queries)

    def test_allocated_days_are_weekdays_only(self):
        """Auto-allocated schedule dates must all be weekdays — Saturday and Sunday must never be inserted."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        inserted_dates = []

        def side_effect(conn, query, params=None):
            if "COUNT(*) AS cnt" in query:
                return pd.DataFrame({"cnt": [0]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Time_Card WHERE TimeCardID" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "Schedule WHERE ScheduleID" in query:
                return empty_df()
            if "INSERT INTO dbo.Schedule" in query and params:
                inserted_dates.append(params[2])
            return None

        with patch(PATCH, side_effect=side_effect):
            autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])

        assert len(inserted_dates) == 10
        for date_str in inserted_dates:
            dt = datetime.strptime(date_str, "%Y%m%d")
            assert dt.weekday() < 5, f"{date_str} falls on a weekend"

    def test_allocated_days_use_regular_pay_type(self):
        """Every auto-allocated schedule entry must use 'Regular' as its pay type."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        inserted_params = []

        def side_effect(conn, query, params=None):
            if "COUNT(*) AS cnt" in query:
                return pd.DataFrame({"cnt": [0]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Time_Card WHERE TimeCardID" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "Schedule WHERE ScheduleID" in query:
                return empty_df()
            if "INSERT INTO dbo.Schedule" in query and params:
                inserted_params.append(params)
            return None

        with patch(PATCH, side_effect=side_effect):
            autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])

        assert all(p[3] == "Regular" for p in inserted_params)

    def test_allocated_days_use_100_percent(self):
        """Salaried employees auto-allocated for a full day must always have Percentage = 100.0."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        inserted_params = []

        def side_effect(conn, query, params=None):
            if "COUNT(*) AS cnt" in query:
                return pd.DataFrame({"cnt": [0]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Time_Card WHERE TimeCardID" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "Schedule WHERE ScheduleID" in query:
                return empty_df()
            if "INSERT INTO dbo.Schedule" in query and params:
                inserted_params.append(params)
            return None

        with patch(PATCH, side_effect=side_effect):
            autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])

        assert all(p[5] == 100.0 for p in inserted_params)

    def test_employee_not_added_if_all_days_already_exist_individually(self):
        """If COUNT is below 10 but every per-day check finds an existing entry, no inserts fire and employee is excluded."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        with patch(PATCH, side_effect=self._side(count=5, hours=8.0, day_exists=True)):
            result = autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001"])
        assert "EMP001" not in result

    def test_returns_empty_list_when_all_employees_fully_allocated(self):
        """When every employee in the list is fully covered, the function must return an empty list."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        with patch(PATCH, return_value=pd.DataFrame({"cnt": [10]})):
            result = autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001", "EMP002", "EMP003"])
        assert result == []

    def test_handles_empty_employee_list(self):
        """An empty input list should return an empty list immediately with no DB calls."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        with patch(PATCH) as mock_rq:
            result = autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", [])
        assert result == []
        assert mock_rq.call_count == 0

    def test_fully_allocated_employee_does_not_block_others(self):
        """A fully-allocated employee must not prevent other employees in the same batch from being processed."""
        from Controllers.timecardAllocationController import autoAllocateSalariedEmployees
        inserts_by_emp = {}

        def side_effect(conn, query, params=None):
            if "COUNT(*) AS cnt" in query:
                emp = params[0] if params else None
                return pd.DataFrame({"cnt": [10]}) if emp == "EMP001" else pd.DataFrame({"cnt": [0]})
            if "PayPeriodHours" in query:
                return pd.DataFrame({"PayPeriodHours": [8.0]})
            if "Time_Card WHERE TimeCardID" in query:
                return pd.DataFrame({"TimeCardID": ["x"]})
            if "Schedule WHERE ScheduleID" in query:
                return empty_df()
            if "INSERT INTO dbo.Schedule" in query and params:
                emp = params[1]
                inserts_by_emp[emp] = inserts_by_emp.get(emp, 0) + 1
            return None

        with patch(PATCH, side_effect=side_effect):
            result = autoAllocateSalariedEmployees(make_conn(), "20250430", "20250421", ["EMP001", "EMP002"])

        assert "EMP001" not in result
        assert "EMP002" in result
        assert inserts_by_emp.get("EMP001", 0) == 0
        assert inserts_by_emp.get("EMP002", 0) == 10


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
