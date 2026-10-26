from odoo import api, fields, models

# '0' = not scored yet; the priority (star) widget shows the remaining five values as stars.
SCORES = [
    ('0', 'Not scored'),
    ('1', 'Poor'),
    ('2', 'Fair'),
    ('3', 'Good'),
    ('4', 'Very good'),
    ('5', 'Excellent'),
]
SCORE_FIELDS = (
    'score_technical', 'score_teamwork', 'score_delivery',
    'score_communication', 'score_ownership', 'score_learning',
)


class TechAppraisalScoreMixin(models.AbstractModel):
    """The six scored criteria shared by manager appraisals and peer reviews."""
    _name = 'tech.appraisal.score.mixin'
    _description = 'Appraisal criteria'

    score_technical = fields.Selection(
        SCORES, string='Technical skill', default='0',
        help='Code quality, system design and problem solving.')
    score_teamwork = fields.Selection(
        SCORES, string='Teamwork', default='0',
        help='Helping teammates, reviewing code and listening to others.')
    score_delivery = fields.Selection(
        SCORES, string='Delivery', default='0',
        help='Finishing work on time, within scope and ready to use.')
    score_communication = fields.Selection(
        SCORES, string='Communication', default='0',
        help='Regular status updates, explaining technical topics clearly, '
             'clear PR descriptions or documents, and asking when unsure.')
    score_ownership = fields.Selection(
        SCORES, string='Ownership & initiative', default='0',
        help='Seeing work through including follow-up bugs, and proposing '
             'solutions to problems without waiting to be told.')
    score_learning = fields.Selection(
        SCORES, string='Learning & knowledge sharing', default='0',
        help='Acting on feedback, and sharing what was learned with the team.')
    avg_score = fields.Float(compute='_compute_avg_score', store=True, digits=(3, 2))

    @api.depends(*SCORE_FIELDS)
    def _compute_avg_score(self):
        for rec in self:
            scores = [int(rec[name]) for name in SCORE_FIELDS if rec[name] and rec[name] != '0']
            rec.avg_score = sum(scores) / len(scores) if scores else 0.0

    def _all_scored(self):
        self.ensure_one()
        return all(self[name] and self[name] != '0' for name in SCORE_FIELDS)
