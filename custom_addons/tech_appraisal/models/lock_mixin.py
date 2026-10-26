from odoo import api, models
from odoo.exceptions import UserError


class TechAppraisalLockMixin(models.AbstractModel):
    """Records that belong to a closed cycle can no longer be created, changed or deleted.

    To change them, HR first sets the cycle back to draft. Module install/update and
    the ``tech_appraisal_unlock`` context key (used by tests) bypass the lock.
    """
    _name = 'tech.appraisal.lock.mixin'
    _description = 'Lock records of closed cycles'

    @api.model
    def _check_cycle_open(self, cycles):
        if self.env.context.get('install_mode') or self.env.context.get('tech_appraisal_unlock'):
            return
        closed = cycles.sudo().filtered(lambda c: c.state == 'closed')
        if closed:
            raise UserError(self.env._(
                "The cycle \"%s\" is closed, so its appraisals and reviews are locked. "
                "Ask HR to set the cycle back to draft if something must be changed.",
                closed[0].name))

    def write(self, vals):
        self._check_cycle_open(self.cycle_id)
        return super().write(vals)

    def unlink(self):
        self._check_cycle_open(self.cycle_id)
        return super().unlink()
