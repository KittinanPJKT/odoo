from odoo import api, fields, models


class TechAppraisalCycle(models.Model):
    _name = 'tech.appraisal.cycle'
    _description = 'Appraisal Cycle'
    _inherit = ['mail.thread']
    _order = 'date_start desc'

    name = fields.Char(required=True, tracking=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    review_deadline = fields.Date(
        tracking=True, help="Date by which every reviewer should have submitted their reviews.")
    state = fields.Selection(
        [('draft', 'Draft'), ('in_progress', 'In Progress'), ('closed', 'Closed')],
        default='draft', required=True, tracking=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    appraisal_ids = fields.One2many('tech.appraisal', 'cycle_id')
    appraisal_count = fields.Integer(compute='_compute_stats')
    pending_review_count = fields.Integer(compute='_compute_stats')
    avg_score = fields.Float(compute='_compute_stats', digits=(3, 2))

    @api.depends('appraisal_ids.avg_score', 'appraisal_ids.state', 'appraisal_ids.review_ids.state')
    def _compute_stats(self):
        for cycle in self:
            done = cycle.appraisal_ids.filtered(lambda a: a.state == 'done')
            cycle.appraisal_count = len(cycle.appraisal_ids)
            cycle.avg_score = sum(done.mapped('avg_score')) / len(done) if done else 0.0
            cycle.pending_review_count = len(
                cycle.appraisal_ids.review_ids.sudo().filtered(lambda r: r.state == 'draft'))

    def write(self, vals):
        result = super().write(vals)
        if 'review_deadline' in vals or 'date_end' in vals:
            for cycle in self:
                cycle.appraisal_ids.review_ids._sync_activity_deadline()
        return result

    def action_start(self):
        """Start the cycle: create every appraisal and ask the teammates to review."""
        self.state = 'in_progress'
        for cycle in self:
            cycle.action_generate_appraisals()
            cycle.action_generate_reviews()

    def action_close(self):
        for cycle in self:
            pending = cycle.appraisal_ids.review_ids.sudo().filtered(lambda r: r.state == 'draft')
            pending._cancel_review_activity()
            cycle.message_post(body=self.env._(
                "Cycle closed. %(count)s review(s) were still pending and are now locked.",
                count=len(pending)))
        self.state = 'closed'

    def action_draft(self):
        self.state = 'draft'

    def action_generate_appraisals(self):
        """Create one appraisal per employee that has none in this cycle."""
        self.ensure_one()
        existing = self.appraisal_ids.employee_id
        employees = self.env['hr.employee'].search([('company_id', '=', self.company_id.id)]) - existing
        self.env['tech.appraisal'].create(
            [{'cycle_id': self.id, 'employee_id': emp.id} for emp in employees])

    def action_generate_reviews(self):
        self.ensure_one()
        self.appraisal_ids.action_generate_reviews()

    def action_open_appraisals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'tech.appraisal',
            'view_mode': 'kanban,list,form',
            'domain': [('cycle_id', '=', self.id)],
            'context': {'default_cycle_id': self.id},
        }

    def action_open_pending_reviews(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Pending reviews"),
            'res_model': 'tech.appraisal.review',
            'view_mode': 'list,form',
            'domain': [('cycle_id', '=', self.id), ('state', '=', 'draft')],
        }
