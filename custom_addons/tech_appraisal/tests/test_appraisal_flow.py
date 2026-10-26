from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import AppraisalCommon


@tagged('post_install', '-at_install')
class TestAppraisalFlow(AppraisalCommon):

    def setUp(self):
        super().setUp()
        self.appraisal = self.env['tech.appraisal'].create(
            {'cycle_id': self.cycle.id, 'employee_id': self.bob.id})

    def test_appraiser_defaults_to_the_direct_manager(self):
        self.assertEqual(self.appraisal.manager_id, self.lead)
        self.assertEqual(self.appraisal.department_id, self.dept)

    def test_one_appraisal_per_employee_and_cycle(self):
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['tech.appraisal'].create({'cycle_id': self.cycle.id, 'employee_id': self.bob.id})

    def test_state_flow(self):
        a = self.appraisal
        self.assertEqual(a.state, 'draft')
        a.action_start_self_review()
        self.assertEqual(a.state, 'self_review')
        a.action_submit_self_review()
        self.assertEqual(a.state, 'manager_review')
        a.action_done()
        self.assertEqual(a.state, 'done')
        a.action_reset()
        self.assertEqual(a.state, 'draft')

    def test_average_ignores_unscored_criteria(self):
        a = self.appraisal
        self.assertEqual(a.avg_score, 0.0)
        a.write({'score_technical': '5', 'score_teamwork': '4', 'score_delivery': '3'})
        self.assertAlmostEqual(a.avg_score, 4.0)
        a.write({'score_communication': '5', 'score_ownership': '5', 'score_learning': '2'})
        self.assertAlmostEqual(a.avg_score, 24 / 6)

    def test_cycle_average_only_counts_finished_appraisals(self):
        done = self.appraisal
        self.score_all(done, '5')
        done.action_done()
        other = self.env['tech.appraisal'].create({'cycle_id': self.cycle.id, 'employee_id': self.carol.id})
        self.score_all(other, '1')  # scored but not done: must not count
        self.assertAlmostEqual(self.cycle.avg_score, 5.0)
        self.assertEqual(self.cycle.appraisal_count, 2)

    def test_peer_average_counts_submitted_reviews_only(self):
        self.appraisal.action_generate_reviews()
        reviews = self.appraisal.review_ids
        self.assertEqual(self.appraisal.review_count, 3)
        self.assertEqual(self.appraisal.peer_avg_score, 0.0)
        first, second, third = reviews
        self.score_all(first, '5')
        first.action_submit()
        self.score_all(second, '3')
        second.action_submit()
        self.score_all(third, '1')  # scored but still a draft: ignored
        self.assertEqual(self.appraisal.review_submitted_count, 2)
        self.assertAlmostEqual(self.appraisal.peer_avg_score, 4.0)

    def test_generating_reviews_skips_self_and_is_idempotent(self):
        self.appraisal.action_generate_reviews()
        self.appraisal.action_generate_reviews()
        reviewers = self.appraisal.review_ids.reviewer_id
        self.assertEqual(reviewers, self.lead | self.carol | self.dave)
        self.assertNotIn(self.bob, reviewers)

    def test_one_review_per_reviewer(self):
        self.appraisal.action_generate_reviews()
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['tech.appraisal.review'].create(
                {'appraisal_id': self.appraisal.id, 'reviewer_id': self.lead.id})

    def test_employee_without_department_is_reviewed_by_manager_only(self):
        loner = self.env['hr.employee'].create({'name': 'No Dept', 'parent_id': self.lead.id})
        appraisal = self.env['tech.appraisal'].create({'cycle_id': self.cycle.id, 'employee_id': loner.id})
        appraisal.action_generate_reviews()
        self.assertEqual(appraisal.review_ids.reviewer_id, self.lead)
