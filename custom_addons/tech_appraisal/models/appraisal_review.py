from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .score_mixin import SCORE_FIELDS

# what a reviewer can change on a review they already submitted
EDITABLE_CONTENT = set(SCORE_FIELDS) | {'comment'}

TODO_ACTIVITY = 'mail.mail_activity_data_todo'
REMIND_DAYS_BEFORE = 2   # start reminding this many days before the deadline
REMIND_EVERY_DAYS = 3    # and at most this often


class TechAppraisalReview(models.Model):
    """One teammate's feedback on one appraisal (peer or manager review)."""
    _name = 'tech.appraisal.review'
    _description = 'Peer Review'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tech.appraisal.score.mixin', 'tech.appraisal.lock.mixin']
    _order = 'cycle_id desc, employee_id, reviewer_id'

    appraisal_id = fields.Many2one('tech.appraisal', required=True, ondelete='cascade', index=True)
    # Stored copies so a reviewer never needs read access to the appraisal itself.
    employee_id = fields.Many2one(related='appraisal_id.employee_id', string='Reviewed employee', store=True)
    cycle_id = fields.Many2one(related='appraisal_id.cycle_id', store=True)
    cycle_state = fields.Selection(related='cycle_id.state')
    deadline = fields.Date(related='cycle_id.review_deadline', store=True)
    is_overdue = fields.Boolean(compute='_compute_is_overdue')
    can_edit = fields.Boolean(
        compute='_compute_can_edit',
        help="A review can be filled in or changed while its cycle is open and, once submitted, "
             "until the end of the deadline day (or until the cycle is closed when there is no deadline).")
    reviewer_id = fields.Many2one('hr.employee', string='Reviewer', required=True, index=True)
    state = fields.Selection([('draft', 'To Do'), ('submitted', 'Submitted')], default='draft', required=True)
    last_reminder_date = fields.Date(readonly=True, copy=False)

    comment = fields.Text(string='Feedback')

    _reviewer_uniq = models.Constraint(
        'UNIQUE(appraisal_id, reviewer_id)', 'This reviewer already has a review for this appraisal.')

    @api.depends('deadline', 'state', 'cycle_state')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_overdue = bool(
                rec.state == 'draft' and rec.cycle_state != 'closed' and rec.deadline and rec.deadline < today)

    def _in_edit_window(self):
        """True while the reviewer may still change this review (the deadline day itself counts)."""
        self.ensure_one()
        if self.cycle_id.state == 'closed':
            return False
        return not self.deadline or fields.Date.context_today(self) <= self.deadline

    @api.depends('deadline', 'state', 'cycle_state')
    def _compute_can_edit(self):
        for rec in self:
            # a review that is still to do can be filled in late (it just shows as overdue)
            rec.can_edit = rec.cycle_state != 'closed' and (rec.state == 'draft' or rec._in_edit_window())

    @api.depends('employee_id', 'reviewer_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.reviewer_id.name or ''} → {rec.employee_id.name or ''}"

    # ------------------------------------------------------------------
    # CRUD hooks
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        appraisals = self.env['tech.appraisal'].browse(
            [v['appraisal_id'] for v in vals_list if v.get('appraisal_id')])
        self._check_cycle_open(appraisals.cycle_id)
        reviews = super().create(vals_list)
        reviews.filtered(lambda r: r.state == 'draft')._schedule_review_activity()
        return reviews

    def write(self, vals):
        """Submitted reviews stay editable by their reviewer until the deadline.

        After that only HR can change them (Reopen). The cycle lock (closed cycles) is
        enforced by the lock mixin for everybody.
        """
        self.check_access('write')  # access errors first, so we never reveal deadline info to outsiders
        submitted = self.filtered(lambda r: r.state == 'submitted')
        if submitted and not (self.env.su or self.env.user.has_group('hr.group_hr_user')):
            late = submitted.filtered(lambda r: not r._in_edit_window())
            if late:
                raise UserError(self.env._(
                    "The deadline for this review has passed, so it can no longer be changed. "
                    "Ask HR to reopen it if something must be corrected."))
        edited = submitted if EDITABLE_CONTENT & set(vals) and 'state' not in vals else self.browse()
        if edited and any(vals.get(name, '1') in (False, '0') for name in SCORE_FIELDS):
            raise UserError(self.env._("A submitted review must keep all six criteria scored."))
        result = super().write(vals)
        for rec in edited:
            rec.sudo().message_post(
                body=self.env._("Review updated by %s.", self.env.user.name),
                subtype_xmlid='mail.mt_note',
                author_id=self.env.user.partner_id.id,
            )
        return result

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_submit(self):
        for rec in self:
            if not rec._all_scored():
                raise UserError(self.env._("Please score all six criteria before submitting."))
        self.state = 'submitted'
        self._cancel_review_activity()

    def action_reopen(self):
        self.state = 'draft'
        self._schedule_review_activity()

    # ------------------------------------------------------------------
    # To-do activities for the reviewer
    # ------------------------------------------------------------------
    def _schedule_review_activity(self):
        for rec in self.sudo():
            user = rec.reviewer_id.user_id
            if not user or rec.cycle_state == 'closed':
                continue
            if rec.activity_ids.filtered(lambda a: a.user_id == user):
                continue
            rec.activity_schedule(
                TODO_ACTIVITY,
                date_deadline=rec.deadline or rec.cycle_id.date_end,
                summary=self.env._("Review %s", rec.employee_id.name),
                note=self.env._("Please score %(name)s on the six criteria and submit your review.",
                                name=rec.employee_id.name),
                user_id=user.id,
            )

    def _cancel_review_activity(self):
        self.sudo().activity_unlink([TODO_ACTIVITY])

    def _sync_activity_deadline(self):
        for rec in self.sudo().filtered(lambda r: r.state == 'draft'):
            rec.activity_ids.write({'date_deadline': rec.deadline or rec.cycle_id.date_end})

    # ------------------------------------------------------------------
    # Reminders (daily cron)
    # ------------------------------------------------------------------
    @api.model
    def _cron_send_reminders(self):
        today = fields.Date.context_today(self)
        due = self.search([
            ('state', '=', 'draft'),
            ('cycle_id.state', '=', 'in_progress'),
            ('deadline', '!=', False),
            ('reviewer_id.user_id', '!=', False),
            ('deadline', '<=', today + timedelta(days=REMIND_DAYS_BEFORE)),
            '|', ('last_reminder_date', '=', False),
            ('last_reminder_date', '<=', today - timedelta(days=REMIND_EVERY_DAYS)),
        ])
        for rec in due:
            partner = rec.reviewer_id.user_id.partner_id
            overdue = rec.deadline < today
            rec.message_notify(
                partner_ids=partner.ids,
                subject=self.env._("Reminder: review %s", rec.employee_id.name),
                body=self.env._(
                    "Your review of %(name)s is %(when)s (deadline %(deadline)s).",
                    name=rec.employee_id.name,
                    when=self.env._("overdue") if overdue else self.env._("due soon"),
                    deadline=rec.deadline),
            )
            # reminders bypass the cycle lock on purpose: only cycles in progress are selected above
            rec.with_context(tech_appraisal_unlock=True).write({'last_reminder_date': today})
        return len(due)
