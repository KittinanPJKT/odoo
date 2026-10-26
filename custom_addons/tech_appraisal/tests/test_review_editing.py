from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from .common import AppraisalCommon

SIX = ('score_technical', 'score_teamwork', 'score_delivery',
       'score_communication', 'score_ownership', 'score_learning')


@tagged('post_install', '-at_install')
class TestReviewEditing(AppraisalCommon):
    """A reviewer can see their history and change a submitted review until the deadline."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.today()
        cls.cycle.review_deadline = cls.today + timedelta(days=5)
        cls.cycle.action_start()
        cls.bob_user = cls.users[cls.bob]
        # bob's review of carol, already submitted with 4 stars everywhere
        cls.review = cls.env['tech.appraisal.review'].search(
            [('reviewer_id', '=', cls.bob.id), ('employee_id', '=', cls.carol.id),
             ('cycle_id', '=', cls.cycle.id)])
        cls.review.write({name: '4' for name in SIX})
        cls.review.action_submit()

    def _edit_as_bob(self, **vals):
        self.review.with_user(self.bob_user).write(vals)

    def _set_deadline(self, days):
        self.cycle.review_deadline = self.today + timedelta(days=days) if days is not None else False

    # -- editing a submitted review -----------------------------------
    def test_can_edit_a_submitted_review_before_the_deadline(self):
        self._edit_as_bob(score_technical='5', comment='Actually better than I thought')
        self.assertEqual(self.review.state, 'submitted')
        self.assertEqual(self.review.score_technical, '5')
        self.assertAlmostEqual(self.review.avg_score, (5 + 4 * 5) / 6, places=2)

    def test_edit_updates_the_peer_average(self):
        appraisal = self.review.appraisal_id
        before = appraisal.peer_avg_score
        self._edit_as_bob(**{name: '2' for name in SIX})
        self.assertGreater(before, appraisal.peer_avg_score)
        self.assertAlmostEqual(appraisal.peer_avg_score, 2.0)

    def test_edit_is_logged_without_leaking_the_content(self):
        self._edit_as_bob(comment='secret opinion')
        notes = self.review.message_ids.filtered(lambda m: 'Review updated' in (m.body or ''))
        self.assertEqual(len(notes), 1)
        self.assertNotIn('secret opinion', notes.body)

    def test_deadline_day_itself_is_still_editable(self):
        self._set_deadline(0)
        self.assertTrue(self.review.can_edit)
        self._edit_as_bob(comment='last minute')
        self.assertEqual(self.review.comment, 'last minute')

    def test_locked_the_day_after_the_deadline(self):
        self._set_deadline(-1)
        self.assertFalse(self.review.can_edit)
        with self.assertRaises(UserError):
            self._edit_as_bob(comment='too late')
        self.assertNotEqual(self.review.comment, 'too late')

    def test_no_deadline_means_editable_until_the_cycle_closes(self):
        self._set_deadline(None)
        self.assertTrue(self.review.can_edit)
        self._edit_as_bob(comment='still fine')
        self.cycle.action_close()
        self.assertFalse(self.review.can_edit)
        with self.assertRaises(UserError):
            self._edit_as_bob(comment='cycle closed')

    def test_closed_cycle_locks_even_before_the_deadline(self):
        self.cycle.action_close()
        self.assertGreater(self.review.deadline, self.today)
        with self.assertRaises(UserError):
            self._edit_as_bob(comment='closed')

    def test_hr_can_reopen_after_the_deadline(self):
        self._set_deadline(-3)
        self.review.with_user(self.hr_user).action_reopen()
        self.assertEqual(self.review.state, 'draft')

    def test_hr_can_correct_after_the_deadline(self):
        self._set_deadline(-3)
        self.review.with_user(self.hr_user).write({'comment': 'corrected by hr'})
        self.assertEqual(self.review.comment, 'corrected by hr')

    def test_a_submitted_review_must_stay_fully_scored(self):
        with self.assertRaises(UserError):
            self._edit_as_bob(score_learning='0')
        self.assertEqual(self.review.score_learning, '4')

    def test_nobody_else_can_edit_my_review(self):
        with self.assertRaises(AccessError):
            self.review.with_user(self.users[self.carol]).write({'comment': 'not yours'})

    # -- reviews still to do ------------------------------------------
    def test_a_late_review_can_still_be_submitted(self):
        todo = self.env['tech.appraisal.review'].search(
            [('reviewer_id', '=', self.bob.id), ('employee_id', '=', self.dave.id),
             ('cycle_id', '=', self.cycle.id)])
        self._set_deadline(-2)
        self.assertTrue(todo.is_overdue)
        self.assertTrue(todo.can_edit)
        todo = todo.with_user(self.bob_user)
        for name in SIX:
            todo[name] = '3'
        todo.action_submit()
        self.assertEqual(todo.state, 'submitted')

    # -- history (My Reviews) -----------------------------------------
    def _my_reviews(self, user):
        action = self.env.ref('tech_appraisal.tech_appraisal_review_action_mine')
        domain = safe_eval(action.domain, {'uid': user.id})
        return self.env['tech.appraisal.review'].with_user(user).search(domain)

    def test_my_reviews_lists_submitted_and_todo(self):
        mine = self._my_reviews(self.bob_user)
        self.assertEqual(mine.reviewer_id, self.bob)
        self.assertEqual(set(mine.mapped('state')), {'draft', 'submitted'})

    def test_my_reviews_keeps_history_of_closed_cycles(self):
        self.cycle.action_close()
        mine = self._my_reviews(self.bob_user)
        self.assertIn(self.review, mine)
        self.assertEqual(mine.cycle_id, self.cycle)

    def test_my_reviews_never_shows_other_peoples_reviews(self):
        mine = self._my_reviews(self.bob_user)
        theirs = self.env['tech.appraisal.review'].search([('reviewer_id', '=', self.carol.id)])
        self.assertTrue(theirs)
        self.assertFalse(mine & theirs)

    def test_my_reviews_opens_grouped_by_cycle(self):
        action = self.env.ref('tech_appraisal.tech_appraisal_review_action_mine')
        self.assertEqual(safe_eval(action.context)['search_default_group_cycle'], 1)
