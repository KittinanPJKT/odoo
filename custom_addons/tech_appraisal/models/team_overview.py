from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError

from .score_mixin import SCORE_FIELDS

# Privacy thresholds: change them here only.
MIN_RESPONSES = 3  # a criterion with fewer respondents is hidden
MIN_TEAM_SIZE = 4  # a team smaller than this is not shown at all

# key, label, marker (so meaning never relies on colour alone), stars that fall in the band, colour
BANDS = (
    ('strength', 'Strength', '▲', ('4', '5'), '#1b7f3b'),
    ('expected', 'Meets expectations', '●', ('3',), '#3f5a80'),
    ('improve', 'Room to improve', '▼', ('1', '2'), '#b45309'),
)
VALID_SCORES = ('1', '2', '3', '4', '5')


class TechAppraisalTeamOverview(models.TransientModel):
    """Aggregated, anonymous per-criterion overview of the latest closed cycle for a team lead."""
    _name = 'tech.appraisal.team.overview'
    _description = 'Team Overview'

    department_id = fields.Many2one('hr.department', readonly=True)
    summary_html = fields.Html(compute='_compute_summary_html', sanitize=False)

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------
    @api.model
    def _check_team_lead(self, department):
        """Only the manager of the department may see its overview (no exception for admins)."""
        leader = department.sudo().manager_id.user_id
        if not leader or leader.id != self.env.uid:
            raise AccessError(self.env._("Only the team lead of this team can see the team overview."))

    @api.model
    def action_open(self):
        department = self.env['hr.department'].sudo().search(
            [('manager_id.user_id', '=', self.env.uid)], limit=1)
        if not department:
            raise AccessError(self.env._("Only a team lead can see the team overview."))
        self._check_team_lead(department)
        overview = self.create({'department_id': department.id})
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Team Overview"),
            'res_model': self._name,
            'res_id': overview.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------
    # Computation (returns aggregates only: no ids, names or free text)
    # ------------------------------------------------------------------
    @api.model
    def _latest_closed_cycle(self):
        return self.env['tech.appraisal.cycle'].sudo().search(
            [('state', '=', 'closed')], order='date_end desc, id desc', limit=1)

    @api.model
    def _compute_team_summary(self, department, cycle=None):
        """Return ``{'status': ..., 'cycle_name': ..., 'criteria': [...]}``.

        status: 'ok' | 'team_too_small' | 'no_closed_round'.
        Each criterion: ``{'criterion_name', 'respondent_count', 'counts', 'hidden_reason'}`` where
        ``counts`` is ``{'strength': n, 'expected': n, 'improve': n}`` or None when hidden.
        """
        self._check_team_lead(department)
        department = department.sudo()

        team_size = self.env['hr.employee'].sudo().search_count([('department_id', '=', department.id)])
        if team_size < MIN_TEAM_SIZE:
            return {'status': 'team_too_small', 'cycle_name': None, 'criteria': []}

        cycle = cycle or self._latest_closed_cycle()
        if not cycle:
            return {'status': 'no_closed_round', 'cycle_name': None, 'criteria': []}

        Review = self.env['tech.appraisal.review'].sudo()
        domain = [
            ('cycle_id', '=', cycle.id),
            ('state', '=', 'submitted'),
            ('employee_id.department_id', '=', department.id),
        ]
        criteria = []
        for name in SCORE_FIELDS:
            groups = Review._read_group(domain + [(name, 'in', VALID_SCORES)], [name], ['__count'])
            by_score = dict(groups)
            total = sum(by_score.values())
            item = {
                'criterion_name': Review._fields[name].string,
                'respondent_count': total,
                'counts': None,
                'hidden_reason': None,
            }
            if total < MIN_RESPONSES:
                item['hidden_reason'] = 'not_enough_responses'
            else:
                item['counts'] = {
                    key: sum(by_score.get(score, 0) for score in scores)
                    for key, _label, _marker, scores, _colour in BANDS
                }
            criteria.append(item)
        return {'status': 'ok', 'cycle_name': cycle.name, 'criteria': criteria}

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    @api.model
    def _render_summary_html(self, summary):
        status = summary['status']
        if status == 'team_too_small':
            return self._render_notice(
                f"This team has fewer than {MIN_TEAM_SIZE} members, so the overview is not shown "
                "to make sure nobody can tell who gave which score.")
        if status == 'no_closed_round':
            return self._render_notice("There is no closed appraisal cycle yet. The overview appears once the first cycle is closed.")

        legend = Markup('').join(
            Markup('<span class="me-3"><span style="color:{c}" aria-hidden="true">{m}</span> {l}</span>').format(
                c=colour, m=marker, l=label)
            for _key, label, marker, _scores, colour in BANDS)
        parts = [
            Markup('<p class="text-muted mb-1">Appraisal cycle: <b>{}</b> (latest closed cycle only)</p>').format(
                summary['cycle_name']),
            Markup('<p class="mb-3">{}</p>').format(legend),
        ]
        for item in summary['criteria']:
            parts.append(self._render_criterion(item))
        return Markup('').join(parts)

    @api.model
    def _render_notice(self, text):
        return Markup('<div class="alert alert-info" role="status">{}</div>').format(text)

    @api.model
    def _render_criterion(self, item):
        head = Markup('<div class="fw-bold">{} <span class="text-muted fw-normal">({} respondents)</span></div>').format(
            item['criterion_name'], item['respondent_count'])
        if item['counts'] is None:
            body = Markup(
                '<div class="text-muted fst-italic">Not enough data to show (fewer than {} respondents)</div>'
            ).format(MIN_RESPONSES)
            return Markup('<div class="mb-4">{}{}</div>').format(head, body)

        total = item['respondent_count']
        segments, labels = [], []
        for key, label, marker, _scores, colour in BANDS:
            count = item['counts'][key]
            pct = round(count * 100 / total)
            labels.append(Markup('<span class="me-3">{} {} {}% ({} people)</span>').format(marker, label, pct, count))
            if count:
                segments.append(Markup(
                    '<div style="width:{w:.4f}%;background:{c};color:#fff;text-align:center;'
                    'line-height:28px;font-size:0.85rem;white-space:nowrap;overflow:hidden" '
                    'title="{t}">{m} {p}%</div>').format(
                        w=count * 100 / total, c=colour, t=label, m=marker, p=pct))
        bar = Markup(
            '<div class="d-flex" role="img" aria-label="{a}" '
            'style="height:28px;border-radius:4px;overflow:hidden;border:1px solid #888">{s}</div>'
        ).format(a=escape(item['criterion_name']), s=Markup('').join(segments))
        return Markup('<div class="mb-4">{}{}<div class="small mt-1">{}</div></div>').format(
            head, bar, Markup('').join(labels))

    @api.depends('department_id')
    def _compute_summary_html(self):
        for rec in self:
            summary = rec._compute_team_summary(rec.department_id)
            rec.summary_html = rec._render_summary_html(summary)
