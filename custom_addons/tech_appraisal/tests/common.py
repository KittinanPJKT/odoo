from odoo.tests import TransactionCase
from odoo.tests.common import new_test_user


class AppraisalCommon(TransactionCase):
    """A 4-person Engineering team (lead + 3 devs) with a user for each, and an empty draft cycle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # the module ships sample cycles; take them out of the way so tests only see their own data
        cls.env['tech.appraisal.cycle'].search([]).write({'state': 'draft'})
        cls.dept = cls.env['hr.department'].create({'name': 'Eng Test'})
        cls.lead, cls.bob, cls.carol, cls.dave = cls.env['hr.employee'].create(
            [{'name': name, 'department_id': cls.dept.id}
             for name in ('Lead Lee', 'Bob Dev', 'Carol Dev', 'Dave Dev')])
        for emp in (cls.bob, cls.carol, cls.dave):
            emp.parent_id = cls.lead
        cls.users = {}
        for emp in (cls.lead, cls.bob, cls.carol, cls.dave):
            login = emp.name.split()[0].lower() + '_t'
            cls.users[emp] = new_test_user(cls.env, login=login, groups='base.group_user')
            emp.user_id = cls.users[emp]
        cls.hr_user = new_test_user(cls.env, login='hr_t', groups='base.group_user,hr.group_hr_user')
        # an employee outside the team, to check nothing leaks across departments
        cls.other_dept = cls.env['hr.department'].create({'name': 'Other Test'})
        cls.outsider = cls.env['hr.employee'].create({'name': 'Out Sider', 'department_id': cls.other_dept.id})
        cls.cycle = cls.env['tech.appraisal.cycle'].create({
            'name': 'Cycle T', 'date_start': '2026-01-01', 'date_end': '2026-03-31',
            'review_deadline': '2026-03-15', 'company_id': cls.env.company.id,
        })

    @classmethod
    def team(cls):
        return cls.lead | cls.bob | cls.carol | cls.dave

    def team_appraisals(self, cycle=None):
        cycle = cycle or self.cycle
        return cycle.appraisal_ids.filtered(lambda a: a.employee_id in self.team())

    def team_reviews(self, cycle=None):
        return self.team_appraisals(cycle).review_ids

    def score_all(self, review, stars='4'):
        review.write({name: stars for name in (
            'score_technical', 'score_teamwork', 'score_delivery',
            'score_communication', 'score_ownership', 'score_learning')})
