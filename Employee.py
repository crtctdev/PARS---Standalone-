class Employee:
    def __init__(self, employee_code, last_name, first_name, dept_code, work_email):
        self.employee_code = employee_code
        self.last_name = last_name
        self.first_name = first_name
        self.dept_code = dept_code
        self.work_email = work_email

    def full_name(self):
        return f"{self.last_name}, {self.first_name}"
    




