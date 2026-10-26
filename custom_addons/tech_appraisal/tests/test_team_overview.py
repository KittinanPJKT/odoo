from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.tech_appraisal.models.score_mixin import SCORE_FIELDS
from odoo.addons.tech_appraisal.models.team_overview import MIN_RESPONSES, MIN_TEAM_SIZE


@tagged('post_install', '-at_install')
class TestTeamOverview(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Overview = cls.env['tech.appraisal.team.overview']
        # the module ships sample cycles; take them out of the way so tests only see their own data
        cls.env['tech.appraisal.cycle'].search([]).write({'state': 'draft'})
        cls.dept = cls.env['hr.department'].create({'name': 'Team A'})
        cls.employees = cls._make_employees(cls.dept, ['Alice Lead', 'Bob Dev', 'Carol Dev', 'Dave Dev'])
        cls.lead_user = new_test_user(cls.env, login='lead_a', groups='base.group_user')
        cls.employees[0].user_id = cls.lead_user
        cls.dept.manager_id = cls.employees[0]  # also grants the team lead group
        cls.cycle = cls._make_cycle('Closed R1', '2026-01-01', '2026-03-31', 'closed')

    # -- helpers -----------------------------------------------------
    @classmethod
    def _make_employees(cls, dept, names):
        return cls.env['hr.employee'].create([{'name': n, 'department_id': dept.id} for n in names])

    @classmethod
    def _make_cycle(cls, name, start, end, state):
        return cls.env['tech.appraisal.cycle'].create(
            {'name': name, 'date_start': start, 'date_end': end, 'state': state})

    @classmethod
    def _review(cls, cycle, reviewee, reviewer, **scores):
        """Create a submitted review; criteria not given in `scores` stay unscored ('0')."""
        # closed cycles are locked, so build the fixture with the lock bypassed
        unlocked = cls.env['tech.appraisal'].with_context(tech_appraisal_unlock=True)
        appraisal = unlocked.search(
            [('cycle_id', '=', cycle.id), ('employee_id', '=', reviewee.id)]
        ) or unlocked.create({'cycle_id': cycle.id, 'employee_id': reviewee.id})
        vals = dict.fromkeys(SCORE_FIELDS, '0')
        vals.update(scores)
        return cls.env['tech.appraisal.review'].with_context(tech_appraisal_unlock=True).create(
            {'appraisal_id': appraisal.id, 'reviewer_id': reviewer.id, 'state': 'submitted', **vals})

    def _summary(self, user=None, department=None, cycle=None):
        overview = self.Overview.with_user(user or self.lead_user)
        return overview._compute_team_summary(department or self.dept, cycle)

    def _criterion(self, summary, field='score_technical'):
        name = self.env['tech.appraisal.review']._fields[field].string
        return next(c for c in summary['criteria'] if c['criterion_name'] == name)

    # -- access ------------------------------------------------------
    def test_non_lead_cannot_read(self):
        outsider = new_test_user(self.env, login='outsider', groups='base.group_user')
        with self.assertRaises(AccessError):
            self._summary(user=outsider)

    def test_lead_of_other_team_cannot_read(self):
        other_dept = self.env['hr.department'].create({'name': 'Team B'})
        other_emp = self._make_employees(other_dept, ['Eve Lead'])
        other_lead = new_test_user(self.env, login='lead_b', groups='base.group_user')
        other_emp.user_id = other_lead
        other_dept.manager_id = other_emp
        with self.assertRaises(AccessError):
            self._summary(user=other_lead, department=self.dept)

    def test_admin_who_is_not_lead_cannot_read(self):
        with self.assertRaises(AccessError):
            self._summary(user=self.env.ref('base.user_admin'))

    def test_open_action_requires_team_lead(self):
        outsider = new_test_user(self.env, login='outsider2', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.Overview.with_user(outsider).action_open()
        action = self.Overview.with_user(self.lead_user).action_open()
        self.assertEqual(action['res_model'], 'tech.appraisal.team.overview')

    def test_team_lead_group_follows_department_manager(self):
        group = self.env.ref('tech_appraisal.group_team_lead')
        self.assertIn(group, self.lead_user.group_ids)
        self.dept.manager_id = self.employees[1]
        self.assertNotIn(group, self.lead_user.group_ids)

    # -- counting ----------------------------------------------------
    def test_counts_per_band(self):
        a, b, c, d = self.employees
        # stars 5 and 4 -> strength, 3 -> expected, 2 and 1 -> improve
        for reviewee, reviewer, stars in ((a, b, '5'), (a, c, '4'), (a, d, '3'), (b, a, '2'), (b, c, '1')):
            self._review(self.cycle, reviewee, reviewer, score_technical=stars)
        item = self._criterion(self._summary())
        self.assertEqual(item['respondent_count'], 5)
        self.assertEqual(item['counts'], {'strength': 2, 'expected': 1, 'improve': 2})

    def test_unscored_answers_are_not_counted(self):
        a, b, c, d = self.employees
        self._review(self.cycle, a, b, score_technical='5')
        self._review(self.cycle, a, c, score_technical='4')
        self._review(self.cycle, a, d, score_technical='3')
        self._review(self.cycle, b, a, score_technical='0')  # not scored: no respondent
        item = self._criterion(self._summary())
        self.assertEqual(item['respondent_count'], 3)
        self.assertEqual(item['counts'], {'strength': 2, 'expected': 1, 'improve': 0})

    def test_draft_reviews_are_not_counted(self):
        a, b, c, d = self.employees
        for reviewer in (b, c, d):
            self._review(self.cycle, a, reviewer, score_technical='5')
        draft = self._review(self.cycle, b, a, score_technical='1')
        draft.with_context(tech_appraisal_unlock=True).state = 'draft'
        self.assertEqual(self._criterion(self._summary())['respondent_count'], 3)

    # -- thresholds --------------------------------------------------
    def test_criterion_below_min_responses_is_hidden(self):
        a, b, c, d = self.employees
        self.assertEqual(MIN_RESPONSES, 3)
        self._review(self.cycle, a, b, score_technical='5', score_teamwork='5')
        self._review(self.cycle, a, c, score_technical='4', score_teamwork='4')
        self._review(self.cycle, a, d, score_technical='3')  # teamwork unscored here
        summary = self._summary()
        technical = self._criterion(summary, 'score_technical')
        teamwork = self._criterion(summary, 'score_teamwork')
        self.assertEqual(technical['respondent_count'], 3)
        self.assertIsNotNone(technical['counts'])
        self.assertEqual(teamwork['respondent_count'], 2)
        self.assertIsNone(teamwork['counts'])
        self.assertTrue(teamwork['hidden_reason'])

    def test_team_of_three_is_too_small(self):
        self.assertEqual(MIN_TEAM_SIZE, 4)
        self.employees[3].department_id = False
        self.assertEqual(self._summary()['status'], 'team_too_small')
        self.employees[3].department_id = self.dept
        self.assertEqual(self._summary()['status'], 'ok')

    def test_no_closed_round(self):
        self.cycle.state = 'in_progress'
        summary = self._summary()
        self.assertEqual(summary['status'], 'no_closed_round')
        self.assertEqual(summary['criteria'], [])

    # -- which round -------------------------------------------------
    def test_only_latest_closed_round_is_used(self):
        a, b, c, d = self.employees
        old = self._make_cycle('Closed old', '2025-01-01', '2025-03-31', 'closed')
        open_cycle = self._make_cycle('Open now', '2026-07-01', '2026-09-30', 'in_progress')
        for reviewer in (b, c, d):
            self._review(old, a, reviewer, score_technical='1')
            self._review(open_cycle, a, reviewer, score_technical='2')
            self._review(self.cycle, a, reviewer, score_technical='5')
        summary = self._summary()
        self.assertEqual(summary['cycle_name'], 'Closed R1')
        self.assertEqual(self._criterion(summary)['counts'], {'strength': 3, 'expected': 0, 'improve': 0})

    def test_reviews_of_other_teams_are_ignored(self):
        a, b, c, d = self.employees
        other_dept = self.env['hr.department'].create({'name': 'Team B'})
        outsiders = self._make_employees(other_dept, ['X One', 'X Two', 'X Three'])
        for reviewer in (b, c, d):
            self._review(self.cycle, a, reviewer, score_technical='5')
            self._review(self.cycle, outsiders[0], reviewer, score_technical='1')
        self.assertEqual(self._criterion(self._summary())['respondent_count'], 3)

    # -- privacy of the result --------------------------------------
    def test_result_has_no_identifying_data(self):
        a, b, c, d = self.employees
        for reviewer in (b, c, d):
            review = self._review(self.cycle, a, reviewer, score_technical='5')
            review.comment = 'very private comment'
        overview = self.Overview.with_user(self.lead_user)
        summary = overview._compute_team_summary(self.dept)
        text = repr(summary) + str(overview._render_summary_html(summary))
        for forbidden in ('Alice', 'Bob', 'Carol', 'Dave', 'lead_a', 'very private comment', 'Team A'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(set(summary), {'status', 'cycle_name', 'criteria'})
        for item in summary['criteria']:
            self.assertEqual(set(item), {'criterion_name', 'respondent_count', 'counts', 'hidden_reason'})
            for value in (item['counts'] or {}).values():
                self.assertIsInstance(value, int)

    def test_rendering_states(self):
        overview = self.Overview.with_user(self.lead_user)
        html = str(overview._render_summary_html(overview._compute_team_summary(self.dept)))
        self.assertIn('Not enough data to show', html)  # nobody has answered yet
        self.cycle.state = 'in_progress'
        html = str(overview._render_summary_html(overview._compute_team_summary(self.dept)))
        self.assertIn('There is no closed appraisal cycle yet', html)
