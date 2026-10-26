from odoo import api, fields, models
from odoo.exceptions import UserError


class TechAppraisalReview(models.Model):
    """One teammate's feedback on one appraisal (peer or manager review)."""
    _name = 'tech.appraisal.review'
    _description = 'Peer Review'
    _inherit = ['tech.appraisal.score.mixin']
    _order = 'cycle_id desc, employee_id, reviewer_id'

    appraisal_id = fields.Many2one('tech.appraisal', required=True, ondelete='cascade', index=True)
    # Stored copies so a reviewer never needs read access to the appraisal itself.
    employee_id = fields.Many2one(related='appraisal_id.employee_id', string='Reviewed employee', store=True)
    cycle_id = fields.Many2one(related='appraisal_id.cycle_id', store=True)
    reviewer_id = fields.Many2one('hr.employee', string='Reviewer', required=True, index=True)
    state = fields.Selection([('draft', 'To Do'), ('submitted', 'Submitted')], default='draft', required=True)

    comment = fields.Text(string='Feedback')

    _reviewer_uniq = models.Constraint(
        'UNIQUE(appraisal_id, reviewer_id)', 'This reviewer already has a review for this appraisal.')

    @api.depends('employee_id', 'reviewer_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.reviewer_id.name or ''} → {rec.employee_id.name or ''}"

    def action_submit(self):
        for rec in self:
            if not rec._all_scored():
                raise UserError(self.env._("Please score all six criteria before submitting."))
        self.state = 'submitted'

    def action_reopen(self):
        self.state = 'draft'
