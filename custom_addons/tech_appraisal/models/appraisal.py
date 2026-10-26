from odoo import api, fields, models

SCORES = [
    ('1', '1 - Poor'),
    ('2', '2 - Fair'),
    ('3', '3 - Good'),
    ('4', '4 - Very good'),
    ('5', '5 - Excellent'),
]


class TechAppraisal(models.Model):
    _name = 'tech.appraisal'
    _description = 'Employee Appraisal'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'cycle_id desc, employee_id'

    cycle_id = fields.Many2one('tech.appraisal.cycle', required=True, ondelete='cascade', tracking=True)
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True)
    manager_id = fields.Many2one(
        'hr.employee', string='Appraiser', compute='_compute_manager_id', store=True, readonly=False)
    company_id = fields.Many2one(related='cycle_id.company_id', store=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('self_review', 'Self Review'),
         ('manager_review', 'Manager Review'), ('done', 'Done')],
        default='draft', required=True, tracking=True)

    score_technical = fields.Selection(SCORES, string='Technical skill')
    score_teamwork = fields.Selection(SCORES, string='Teamwork')
    score_delivery = fields.Selection(SCORES, string='Delivery')
    avg_score = fields.Float(compute='_compute_avg_score', store=True, digits=(3, 2))

    self_comment = fields.Text(string='Employee comment')
    manager_comment = fields.Text(string='Appraiser comment')

    _employee_cycle_uniq = models.Constraint(
        'UNIQUE(cycle_id, employee_id)', 'An employee can only have one appraisal per cycle.')

    @api.depends('employee_id.parent_id')
    def _compute_manager_id(self):
        for rec in self:
            rec.manager_id = rec.employee_id.parent_id

    @api.depends('score_technical', 'score_teamwork', 'score_delivery')
    def _compute_avg_score(self):
        for rec in self:
            scores = [int(s) for s in (rec.score_technical, rec.score_teamwork, rec.score_delivery) if s]
            rec.avg_score = sum(scores) / len(scores) if scores else 0.0

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
