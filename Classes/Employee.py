class Employee:
    """
    Represents an employee record within the PARS system.

    Constructed from EmployeeInformation data and used throughout the application
    for session state, UI dropdowns, and permission checks. The presence of a
    ManagingDepartment value is the sole indicator of manager status.
    """
    def __init__(self, employee_code, last_name, first_name, dept_code, work_email, managing_department, pay_period_hours):
        self.employee_code = employee_code
        self.last_name = last_name
        self.first_name = first_name
        self.dept_code = dept_code
        self.work_email = work_email
        self.managing_department = managing_department
        self.pay_period_hours = pay_period_hours

    def full_name(self):
        """
        Returns the employee's display name in Last, First format.

        Returns:
            str: Full name formatted as 'LastName, FirstName'.
        """
        return f"{self.last_name}, {self.first_name}"

    def isManager(self):
        """
        Determines whether the employee has manager-level access.

        Returns:
            bool: True if the employee has a ManagingDepartment assigned, False otherwise.
        """
        return self.managing_department is not None
