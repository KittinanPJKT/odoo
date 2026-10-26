from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AppraisalCommon


@tagged('post_install', '-at_install')
class TestCycleLifecycle(AppraisalCommon):

    def _start(self):
        self.cycle.action_start()
        return self.team_reviews()

    # -- starting a cycle ---------------------------------------------
    def test_start_creates_appraisals_and_reviews(self):
        reviews = self._start()
        self.assertEqual(self.cycle.state, 'in_progress')
        self.assertEqual(self.team_appraisals().employee_id, self.team())
        # each person is reviewed by every teammate and by their manager, never by themselves
        self.assertEqual(len(reviews), 12)
        for appraisal in self.team_appraisals():
            expected = (self.team() | appraisal.employee_id.parent_id) - appraisal.employee_id
            self.assertEqual(appraisal.review_ids.reviewer_id, expected)
        self.assertEqual(self.env['tech.appraisal'].search([
            ('cycle_id', '=', self.cycle.id), ('employee_id', '=', self.outsider.id)]).review_count, 0)

    def test_start_twice_does_not_duplicate(self):
        self._start()
        self.cycle.action_generate_appraisals()
        self.cycle.action_generate_reviews()
        self.assertEqual(len(self.team_reviews()), 12)

    # -- activities ----------------------------------------------------
    def test_reviewers_get_a_todo_with_the_deadline(self):
        review = self._start().filtered(lambda r: r.reviewer_id == self.bob)[0]
        activity = review.activity_ids
        self.assertEqual(len(activity), 1)
        self.assertEqual(activity.user_id, self.users[self.bob])
        self.assertEqual(activity.date_deadline, self.cycle.review_deadline)

    def test_submitting_clears_the_todo_and_reopening_restores_it(self):
        review = self._start().filtered(lambda r: r.reviewer_id == self.bob)[0]
        self.score_all(review)
        review.with_user(self.users[self.bob]).action_submit()
        self.assertEqual(review.state, 'submitted')
        self.assertFalse(review.activity_ids)
        review.action_reopen()
        self.assertEqual(len(review.activity_ids), 1)

    def test_changing_the_deadline_moves_the_todos(self):
        reviews = self._start()
        new_deadline = fields.Date.to_date('2026-03-20')
        self.cycle.review_deadline = new_deadline
        self.assertEqual(set(reviews.activity_ids.mapped('date_deadline')), {new_deadline})

    def test_deadline_falls_back_to_cycle_end(self):
        self.cycle.review_deadline = False
        review = self._start()[0]
        self.assertEqual(review.activity_ids.date_deadline, self.cycle.date_end)

    # -- submitting ----------------------------------------------------
    def test_submit_needs_all_six_criteria(self):
        review = self._start()[0]
        review.write({'score_technical': '5', 'score_teamwork': '4', 'score_delivery': '3'})
        with self.assertRaises(UserError):
            review.action_submit()
        self.score_all(review)
        review.action_submit()
        self.assertEqual(review.state, 'submitted')

    # -- overdue -------------------------------------------------------
    def test_is_overdue(self):
        reviews = self._start()
        review = reviews[0]
        self.cycle.review_deadline = fields.Date.today() - timedelta(days=1)
        self.assertTrue(review.is_overdue)
        self.score_all(review)
        review.action_submit()
        self.assertFalse(review.is_overdue)
        other = reviews[1]
        self.assertTrue(other.is_overdue)
        self.cycle.review_deadline = fields.Date.today() + timedelta(days=5)
        self.assertFalse(other.is_overdue)

    # -- closing and locking ------------------------------------------
    def test_closing_cancels_pending_todos_and_logs_it(self):
        reviews = self._start()
        self.assertTrue(reviews.activity_ids)
        self.cycle.action_close()
        self.assertEqual(self.cycle.state, 'closed')
        self.assertFalse(reviews.activity_ids)
        total = len(self.cycle.appraisal_ids.review_ids)
        self.assertIn(f'{total} review(s) were still pending', self.cycle.message_ids[0].body)

    def test_closed_cycle_locks_reviews_and_appraisals(self):
        reviews = self._start()
        review, appraisal = reviews[0], reviews[0].appraisal_id
        self.cycle.action_close()
        for action in (
            lambda: review.write({'comment': 'late edit'}),
            lambda: self.score_all(review),
            lambda: review.unlink(),
            lambda: appraisal.write({'manager_comment': 'late edit'}),
            lambda: appraisal.action_start_self_review(),
            lambda: self.env['tech.appraisal.review'].create(
                {'appraisal_id': appraisal.id, 'reviewer_id': self.outsider.id}),
            lambda: self.env['tech.appraisal'].create(
                {'cycle_id': self.cycle.id, 'employee_id': self.outsider.id}),
        ):
            with self.assertRaises(UserError), self.cr.savepoint():
                action()

    def test_locked_even_for_hr(self):
        review = self._start()[0]
        self.cycle.action_close()
        with self.assertRaises(UserError):
            review.with_user(self.hr_user).write({'comment': 'x'})

    def test_reopening_the_cycle_unlocks_it(self):
        review = self._start()[0]
        self.cycle.action_close()
        self.cycle.action_draft()
        review.write({'comment': 'fixed after reopening'})
        self.assertEqual(review.comment, 'fixed after reopening')

    def test_other_cycles_are_not_locked_by_a_closed_one(self):
        closed = self._start()[0]
        self.cycle.action_close()
        other_cycle = self.env['tech.appraisal.cycle'].create(
            {'name': 'Next', 'date_start': '2026-04-01', 'date_end': '2026-06-30'})
        other_cycle.action_start()
        other = self.team_reviews(other_cycle)[0]
        other.write({'comment': 'fine'})
        self.assertEqual(other.comment, 'fine')
        self.assertTrue(closed.cycle_id.state == 'closed')

    # -- reminders (cron) ---------------------------------------------
    def _reminders(self):
        return self.env['tech.appraisal.review']._cron_send_reminders()

    def _total(self):
        # the whole cycle also covers the sample employees that ship with the module;
        # only reviewers who have a user can be reminded
        return len(self.cycle.appraisal_ids.review_ids.filtered('reviewer_id.user_id'))

    def test_cron_reminds_due_reviews_once_per_period(self):
        reviews = self._start()
        today = fields.Date.today()
        self.cycle.review_deadline = today + timedelta(days=1)
        self.assertEqual(self._reminders(), self._total())
        self.assertEqual(set(reviews.mapped('last_reminder_date')), {today})
        self.assertEqual(self._reminders(), 0)  # not again the same day
        reviews.with_context(tech_appraisal_unlock=True).last_reminder_date = today - timedelta(days=3)
        self.assertEqual(self._reminders(), 12)  # only the ones we aged are due again

    def test_cron_sends_a_message_to_the_reviewer(self):
        review = self._start().filtered(lambda r: r.reviewer_id == self.bob)[0]
        self.cycle.review_deadline = fields.Date.today() - timedelta(days=2)
        self._reminders()
        message = self.env['mail.message'].search(
            [('model', '=', 'tech.appraisal.review'), ('res_id', '=', review.id)], limit=1)
        self.assertIn(self.users[self.bob].partner_id, message.partner_ids)
        self.assertIn('overdue', message.body)

    def test_cron_skips_submitted_far_off_closed_and_no_deadline(self):
        reviews = self._start()
        today = fields.Date.today()
        # deadline far away
        self.cycle.review_deadline = today + timedelta(days=30)
        self.assertEqual(self._reminders(), 0)
        # no deadline at all
        self.cycle.review_deadline = False
        self.assertEqual(self._reminders(), 0)
        # submitted reviews are not reminded
        self.cycle.review_deadline = today
        done = reviews[0]
        self.score_all(done)
        done.action_submit()
        self.assertEqual(self._reminders(), self._total() - 1)
        # closed cycle
        reviews.with_context(tech_appraisal_unlock=True).last_reminder_date = False
        self.cycle.action_close()
        self.assertEqual(self._reminders(), 0)
