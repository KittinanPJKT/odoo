from odoo import api, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    @api.model_create_multi
    def create(self, vals_list):
        departments = super().create(vals_list)
        departments._sync_team_lead_group()
        return departments

    def write(self, vals):
        old_leaders = self.manager_id.user_id if 'manager_id' in vals else self.env['res.users']
        result = super().write(vals)
        if 'manager_id' in vals:
            self._sync_team_lead_group(old_leaders)
        return result

    def _sync_team_lead_group(self, old_leaders=None):
        """Keep the 'Team Lead' group in sync with who manages a department."""
        group = self.env.ref('tech_appraisal.group_team_lead', raise_if_not_found=False)
        if not group:
            return
        group = group.sudo()
        new_leaders = self.sudo().manager_id.user_id
        new_leaders.write({'group_ids': [(4, group.id)]})
        for user in (old_leaders or self.env['res.users']).sudo() - new_leaders:
            still_leads = self.sudo().search_count([('manager_id.user_id', '=', user.id)])
            if not still_leads:
                user.write({'group_ids': [(3, group.id)]})
