import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, call

DB_PATCH = "Controllers.DB.run_query"


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_user(email="emp@crtct.org", name="Test User"):
    return {"email": email, "name": name}

def make_conn():
    return MagicMock()

def make_employee_df(code="A1L7", last="Doe", first="John", dept="IT",
                     email="emp@crtct.org", managing=None, hours=8.0):
    return pd.DataFrame([{
        "EmployeeCode": code,
        "EmployeeLast": last,
        "EmployeeFirst": first,
        "DepartmentCode": dept,
        "WorkEmail": email,
        "ManagingDepartment": managing,
        "PayPeriodHours": hours,
    }])


# ── run_query ─────────────────────────────────────────────────────────────────

class TestRunQuery:
    def test_closes_cursor_after_select(self):
        """cursor.close() must be called after a SELECT query so the connection is free for the next call."""
        from Controllers.DB import run_query
        cursor = MagicMock()
        cursor.description = [("col",)]
        cursor.fetchall.return_value = [("value",)]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        run_query(conn, "SELECT 1", [])
        cursor.close.assert_called_once()

    def test_closes_cursor_after_write(self):
        """cursor.close() must also be called after INSERT/UPDATE/DELETE queries."""
        from Controllers.DB import run_query
        cursor = MagicMock()
        cursor.description = None
        conn = MagicMock()
        conn.cursor.return_value = cursor
        run_query(conn, "UPDATE dbo.Foo SET x = 1", [])
        cursor.close.assert_called_once()

    def test_returns_none_on_exception(self):
        """If the query raises, run_query must swallow the error and return None rather than propagating."""
        from Controllers.DB import run_query
        conn = MagicMock()
        conn.cursor.side_effect = Exception("DB error")
        result = run_query(conn, "SELECT 1", [])
        assert result is None

    def test_returns_dataframe_for_select(self):
        """A SELECT query should return a DataFrame with the columns from cursor.description."""
        from Controllers.DB import run_query
        cursor = MagicMock()
        cursor.description = [("Name",), ("Age",)]
        cursor.fetchall.return_value = [("Alice", 30)]
        conn = MagicMock()
        conn.cursor.return_value = cursor
        result = run_query(conn, "SELECT Name, Age FROM Foo", [])
        assert list(result.columns) == ["Name", "Age"]
        assert result.iloc[0]["Name"] == "Alice"

    def test_returns_none_for_write_query(self):
        """INSERT/UPDATE/DELETE queries with no result set must return None."""
        from Controllers.DB import run_query
        cursor = MagicMock()
        cursor.description = None
        conn = MagicMock()
        conn.cursor.return_value = cursor
        result = run_query(conn, "DELETE FROM Foo WHERE Id = 1", [])
        assert result is None

    def test_commits_after_write_query(self):
        """conn.commit() must be called after a successful write query to persist the change."""
        from Controllers.DB import run_query
        cursor = MagicMock()
        cursor.description = None
        conn = MagicMock()
        conn.cursor.return_value = cursor
        run_query(conn, "INSERT INTO Foo VALUES (1)", [])
        conn.commit.assert_called_once()


# ── setLoggedInUser ───────────────────────────────────────────────────────────

class TestSetLoggedInUser:
    def test_returns_empty_list_when_query_returns_none(self):
        """If run_query returns None (e.g. a DB error), setLoggedInUser must return [] rather than raising."""
        from Controllers.DB import setLoggedInUser
        with patch(DB_PATCH, return_value=None):
            result = setLoggedInUser(make_conn(), make_user())
        assert result == []

    def test_returns_empty_list_when_query_returns_empty_df(self):
        """If fn_GetEmployee finds no row for the email, an empty list should be returned — not an AttributeError."""
        from Controllers.DB import setLoggedInUser
        with patch(DB_PATCH, return_value=pd.DataFrame()):
            result = setLoggedInUser(make_conn(), make_user())
        assert result == []

    def test_returns_employee_for_known_email(self):
        """A valid email that matches exactly one fn_GetEmployee row should return a list with one Employee."""
        from Controllers.DB import setLoggedInUser
        df = make_employee_df()
        with patch(DB_PATCH, return_value=df):
            result = setLoggedInUser(make_conn(), make_user())
        assert len(result) == 1
        assert result[0].employee_code == "A1L7"

    def test_employee_attributes_mapped_correctly(self):
        """All Employee fields must be populated from the correct DataFrame columns."""
        from Controllers.DB import setLoggedInUser
        df = make_employee_df(code="X1", last="Smith", first="Jane", dept="HR",
                              email="jane@crtct.org", managing="DEPT01", hours=7.5)
        with patch(DB_PATCH, return_value=df):
            result = setLoggedInUser(make_conn(), make_user(email="jane@crtct.org"))
        emp = result[0]
        assert emp.last_name == "Smith"
        assert emp.first_name == "Jane"
        assert emp.dept_code == "HR"
        assert emp.work_email == "jane@crtct.org"
        assert emp.managing_department == "DEPT01"
        assert emp.pay_period_hours == 7.5

    def test_is_manager_true_when_managing_department_set(self):
        """An employee with a non-None ManagingDepartment must report isManager() == True."""
        from Controllers.DB import setLoggedInUser
        df = make_employee_df(managing="DEPT01")
        with patch(DB_PATCH, return_value=df):
            result = setLoggedInUser(make_conn(), make_user())
        assert result[0].isManager() is True

    def test_is_manager_false_when_managing_department_none(self):
        """An employee with ManagingDepartment = None must report isManager() == False."""
        from Controllers.DB import setLoggedInUser
        df = make_employee_df(managing=None)
        with patch(DB_PATCH, return_value=df):
            result = setLoggedInUser(make_conn(), make_user())
        assert result[0].isManager() is False

    def test_passes_email_to_query(self):
        """The user's email address must be forwarded as the query parameter to fn_GetEmployee."""
        from Controllers.DB import setLoggedInUser
        with patch(DB_PATCH, return_value=pd.DataFrame()) as mock_rq:
            setLoggedInUser(make_conn(), make_user(email="specific@crtct.org"))
        params = mock_rq.call_args[0][2]
        assert "specific@crtct.org" in params
