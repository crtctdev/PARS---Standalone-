class Employee:
    def __init__(self, employee_code, last_name, first_name, dept_code, work_email,managing_department, pay_period_hours):
        self.employee_code = employee_code
        self.last_name = last_name
        self.first_name = first_name
        self.dept_code = dept_code
        self.work_email = work_email
        self.managing_department = managing_department
        self.pay_period_hours = pay_period_hours

    def full_name(self):
        return f"{self.last_name}, {self.first_name}"
    def isManager(self):
        return self.managing_department is not None
    




