from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import AppraisalCommon


@tagged('post_install', '-at_install')
class TestSecurity(AppraisalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cycle.action_start()
        cls.Review = cls.env['tech.appraisal.review']
        cls.Appraisal = cls.env['tech.appraisal']

    def _as(self, employee):
        return self.users[employee]

    def _review(self, reviewer, reviewee):
        return self.Review.search([('reviewer_id', '=', reviewer.id), ('employee_id', '=', reviewee.id),
                                   ('cycle_id', '=', self.cycle.id)])

    # -- reviews -------------------------------------------------------
    def test_reviewer_sees_only_their_own_reviews(self):
        seen = self.Review.with_user(self._as(self.bob)).search([('cycle_id', '=', self.cycle.id)])
        self.assertTrue(seen)
        self.assertEqual(seen.reviewer_id, self.bob)

    def test_reviewed_employee_cannot_see_who_reviewed_them(self):
        about_bob = self.Review.with_user(self._as(self.bob)).search(
            [('employee_id', '=', self.bob.id), ('cycle_id', '=', self.cycle.id)])
        self.assertFalse(about_bob)
        bob_appraisal = self.Appraisal.search(
            [('employee_id', '=', self.bob.id), ('cycle_id', '=', self.cycle.id)])
        self.assertFalse(bob_appraisal.with_user(self._as(self.bob)).review_ids)

    def test_reviewed_employee_still_sees_the_aggregate(self):
        review = self._review(self.carol, self.bob)
        self.score_all(review, '5')
        review.action_submit()
        bob_appraisal = self.Appraisal.search(
            [('employee_id', '=', self.bob.id), ('cycle_id', '=', self.cycle.id)])
        self.assertAlmostEqual(bob_appraisal.with_user(self._as(self.bob)).peer_avg_score, 5.0)

    def test_reviewer_can_fill_in_their_own_review_only(self):
        own = self._review(self.bob, self.carol).with_user(self._as(self.bob))
        self.score_all(own, '4')
        own.action_submit()
        self.assertEqual(own.state, 'submitted')
        other = self._review(self.carol, self.dave).with_user(self._as(self.bob))
        with self.assertRaises(AccessError):
            other.write({'comment': 'not mine'})

    def test_manager_reads_submitted_feedback_on_reports_but_cannot_edit(self):
        review = self._review(self.carol, self.bob)
        as_lead = self.Review.with_user(self._as(self.lead))
        self.assertNotIn(review, as_lead.search([]))  # still a draft
        self.score_all(review, '4')
        review.action_submit()
        self.assertIn(review, as_lead.search([]))
        with self.assertRaises(AccessError):
            review.with_user(self._as(self.lead)).write({'comment': 'edited by manager'})

    def test_hr_sees_everything(self):
        total = self.Review.search_count([('cycle_id', '=', self.cycle.id)])
        self.assertEqual(self.Review.with_user(self.hr_user).search_count([('cycle_id', '=', self.cycle.id)]), total)

    def test_employee_cannot_create_reviews_or_cycles(self):
        user = self._as(self.bob)
        with self.assertRaises(AccessError):
            self.Review.with_user(user).create(
                {'appraisal_id': self.team_appraisals()[0].id, 'reviewer_id': self.bob.id})
        with self.assertRaises(AccessError):
            self.env['tech.appraisal.cycle'].with_user(user).create(
                {'name': 'Mine', 'date_start': '2026-01-01', 'date_end': '2026-02-01'})

    # -- appraisals ----------------------------------------------------
    def test_employee_sees_only_their_own_appraisal(self):
        seen = self.Appraisal.with_user(self._as(self.bob)).search(
            [('cycle_id', '=', self.cycle.id), ('employee_id', 'in', self.team().ids)])
        self.assertEqual(seen.employee_id, self.bob)

    def test_manager_sees_their_reports_appraisals(self):
        seen = self.Appraisal.with_user(self._as(self.lead)).search(
            [('cycle_id', '=', self.cycle.id), ('employee_id', 'in', self.team().ids)])
        self.assertEqual(seen.employee_id, self.team())

    def test_only_hr_manages_cycles(self):
        cycles = self.env['tech.appraisal.cycle']
        self.assertTrue(cycles.with_user(self._as(self.bob)).search([]))  # may read
        with self.assertRaises(AccessError):
            self.cycle.with_user(self._as(self.bob)).write({'name': 'renamed'})
        self.cycle.with_user(self.hr_user).write({'name': 'renamed by hr'})
        self.assertEqual(self.cycle.name, 'renamed by hr')
