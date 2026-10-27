# Run through `odoo-bin shell` (see entrypoint.sh): creates two demo logins for the sample team.
# Idempotent. The password comes from $DEMO_PASSWORD (default: demo1234) and is for local use only.
import os

password = os.environ.get('DEMO_PASSWORD', 'demo1234')
users = self.env['res.users']
for login, name, emp_xmlid in (
    ('somchai', 'Somchai Prasert', 'tech_appraisal.emp_somchai'),
    ('malee', 'Malee Chaiyo', 'tech_appraisal.emp_malee'),
):
    employee = self.env.ref(emp_xmlid, raise_if_not_found=False)
    if not employee:
        print('sample employee missing, skipping', login)
        continue
    user = users.search([('login', '=', login)])
    if not user:
        user = users.create({
            'name': name, 'login': login, 'password': password,
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
    employee.user_id = user
    print('demo user ready:', login)

department = self.env.ref('tech_appraisal.dept_engineering', raise_if_not_found=False)
if department:
    department._sync_team_lead_group()  # gives the Team Lead group to the department manager's user
self.env.cr.commit()
