# PARS — Payroll Allocation Recording System

PARS is an internal Streamlit web application used by CRT to manage, allocate, and approve employee timecards each pay period. Employees acknowledge their own timecards, managers approve them, and admins import payroll data and export allocation reports.

---

## Overview

### Who Uses It

| Role | Access |
|---|---|
| **Employee** | Views and acknowledges their own timecard allocations |
| **Manager** | All of the above, plus the Approval Report Manager to approve their department's timecards |
| **Admin** | All of the above, plus importing pay period data from Paycom and exporting allocation reports to Excel |

Roles are determined automatically from the database. Admin status is checked against `dbo.Admins`. Manager status is determined by whether the employee has a `ManagingDepartment` assigned.

### Main Features

- **Timecard Allocations** — View each timecard row for a pay period, allocate hours across fund codes and task codes, and track acknowledgement/approval status. Includes a hover tooltip showing fund code hour breakdowns per row.
- **Approval Report Manager** — Manager-facing view showing approval status across all employees in their department.
- **Import** *(Admin only)* — Upload a Paycom Excel export to populate `Time_Card` and `Schedule` records for a pay period. Salaried employees not in the file are auto-allocated at 100%.
- **Export** *(Admin only)* — Select one or more pay periods and download a formatted Excel report sourced from `fn_GetExport`.

### Scheduled Jobs

Three background jobs run on Windows Task Scheduler:

| Job | File | Purpose |
|---|---|---|
| Remind employees | `Jobs/remind_unacknowledged.py` | Emails employees who have not yet acknowledged their timecards |
| Remind managers | `Jobs/remind_managers.py` | Emails managers who have acknowledged-but-unapproved timecards waiting on them |
| Notify manager on acknowledge | `Jobs/notify_manager_on_acknowledge.py` | Fires immediately when an employee acknowledges — emails their manager with the current and any other pending timecards |

---

## Databases

PARS connects to two SQL Server databases on **CRT-SQL** using Windows Integrated Authentication (no username/password required — runs as the logged-in Windows user).

### `PARS` (primary database)

All application data lives here.

| Object | Type | Purpose |
|---|---|---|
| `dbo.Time_Card` | Table | One row per employee per pay period — stores approval, acknowledged, approved-by |
| `dbo.Schedule` | Table | Individual date/pay-type rows within a timecard |
| `dbo.Record` | Table | Allocation rows (task, fund, hours) tied to a Schedule entry |
| `dbo.Admins` | Table | Email addresses of users with admin access |
| `dbo.Activities` | Table | Task code/description lookup |
| `dbo.Funds` | Table | Fund code/description lookup |
| `dbo.vw_EmployeeInformation` | View | Employee details including department, pay period hours, and manager |
| `dbo.vw_PayPeriods` | View | Pay period start/end date boundaries |
| `dbo.fn_GetEmployee` | TVF | Returns employee record(s) by email — used at login |
| `dbo.fn_GetTimeCards` | TVF | Returns timecard state rows — used by the notify job |
| `dbo.fn_GetExport` | TVF | Returns formatted allocation data for Excel export |
| `dbo.fn_DetailedApprovalReport` | TVF | Returns approval status for all employees under a manager |

### `CRT_INFO` (secondary database)

| Object | Type | Purpose |
|---|---|---|
| `dbo.ADUsers` | Table | Active Directory user records — queried for fund code percentages (`FundCode`, `Percentage`) per employee |

---

## Running Locally

### Prerequisites

- Python 3.11
- ODBC Driver 17 for SQL Server
- Access to CRT-SQL via Windows Integrated Authentication
- `.streamlit/secrets.toml` with Azure AD credentials (not committed — contact an admin)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Start the App

```bash
streamlit run main.py
```

---

## Running the Tests

Tests use `pytest` and mock all database and HTTP calls — no live DB connection required.

### Run All Tests

```bash
py -m pytest tests/ -v
```

### Run a Specific File

```bash
py -m pytest tests/test_DB.py -v
py -m pytest tests/test_timecardAllocationController.py -v
py -m pytest tests/test_notify_manager.py -v
py -m pytest tests/test_remind_jobs.py -v
```

### Test Coverage by File

| File | What It Tests |
|---|---|
| `tests/test_DB.py` | `run_query` (cursor lifecycle, exception handling) and `setLoggedInUser` (None guard, attribute mapping, manager detection) |
| `tests/test_timecardAllocationController.py` | Pay period formatting, timecard state checks, approval/acknowledgement updates, fund lookups, allocation save/delete, import logic, and auto-allocation for salaried employees |
| `tests/test_notify_manager.py` | Manager notification email — format helpers, email body construction, Graph API send, full `notify_manager` flow, `getFundAllocations`, and `changeTimecardState` ApprovedBy preservation |
| `tests/test_remind_jobs.py` | Weekly reminder jobs for unacknowledged employees and unapproved managers |
