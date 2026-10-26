from odoo import api, fields, models


class TechAppraisal(models.Model):
    _name = 'tech.appraisal'
    _description = 'Employee Appraisal'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tech.appraisal.score.mixin', 'tech.appraisal.lock.mixin']
    _order = 'cycle_id desc, employee_id'

    cycle_id = fields.Many2one('tech.appraisal.cycle', required=True, ondelete='cascade', tracking=True)
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True)
    manager_id = fields.Many2one(
        'hr.employee', string='Appraiser', compute='_compute_manager_id', store=True, readonly=False)
    company_id = fields.Many2one(related='cycle_id.company_id', store=True)
    cycle_state = fields.Selection(related='cycle_id.state')
    state = fields.Selection(
        [('draft', 'Draft'), ('self_review', 'Self Review'),
         ('manager_review', 'Manager Review'), ('done', 'Done')],
        default='draft', required=True, tracking=True)

    self_comment = fields.Text(string='Employee comment')
    manager_comment = fields.Text(string='Appraiser comment')

    review_ids = fields.One2many('tech.appraisal.review', 'appraisal_id')
    review_count = fields.Integer(compute='_compute_peer_stats', store=True)
    review_submitted_count = fields.Integer(compute='_compute_peer_stats', store=True)
    peer_avg_score = fields.Float(compute='_compute_peer_stats', store=True, digits=(3, 2))

    _employee_cycle_uniq = models.Constraint(
        'UNIQUE(cycle_id, employee_id)', 'An employee can only have one appraisal per cycle.')

    @api.model_create_multi
    def create(self, vals_list):
        cycles = self.env['tech.appraisal.cycle'].browse([v['cycle_id'] for v in vals_list if v.get('cycle_id')])
        self._check_cycle_open(cycles)
        return super().create(vals_list)

    @api.depends('employee_id.parent_id')
    def _compute_manager_id(self):
        for rec in self:
            rec.manager_id = rec.employee_id.parent_id

    @api.depends('review_ids.state', 'review_ids.avg_score')
    def _compute_peer_stats(self):
        # sudo: the appraised employee must not see individual reviews, only the aggregate.
        for rec in self:
            reviews = rec.review_ids.sudo()
            submitted = reviews.filtered(lambda r: r.state == 'submitted')
            rec.review_count = len(reviews)
            rec.review_submitted_count = len(submitted)
            rec.peer_avg_score = sum(submitted.mapped('avg_score')) / len(submitted) if submitted else 0.0

    def action_generate_reviews(self):
        """Ask every teammate (same department) and the direct manager to review the employee."""
        Review = self.env['tech.appraisal.review']
        for rec in self:
            emp = rec.employee_id
            reviewers = self.env['hr.employee']
            if emp.department_id:
                reviewers |= self.env['hr.employee'].search([('department_id', '=', emp.department_id.id)])
            reviewers |= emp.parent_id
            reviewers -= emp
            reviewers -= rec.review_ids.reviewer_id
            Review.create([{'appraisal_id': rec.id, 'reviewer_id': r.id} for r in reviewers])

    @api.depends('employee_id', 'cycle_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.employee_id.name or ''} - {rec.cycle_id.name or ''}"

    def action_start_self_review(self):
        self.state = 'self_review'

    def action_submit_self_review(self):
        self.state = 'manager_review'

    def action_done(self):
        self.state = 'done'

    def action_reset(self):
        self.state = 'draft'
