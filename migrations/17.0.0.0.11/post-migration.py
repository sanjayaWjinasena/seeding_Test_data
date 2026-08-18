# -*- coding: utf-8 -*-
"""v0.0.11 upgrade -- fix module load order.

v0.0.10's diagnostic log showed 'seeding_Test_data (507/771)' loading
BEFORE Fix-repair, BugFix-Sales, and studio_usermodel_migration.
Result: when the post-migration hook ran, res.partner._fields didn't
contain x_studio_vat_registration_status et al. because their
declaring modules hadn't loaded yet. The customer seeder saw
`Partner._fields.get('x_studio_...')` return None and silently
skipped every Studio field on every partner row.

v0.0.11 adds those sister modules to the manifest `depends` list.
Odoo's module load order is topological on `depends`, so the sisters
now load first, their fields are in _fields when this migration
runs, and the seeder writes them.

Also re-triggers the seed so the 99 customers get their missing
Studio + property values back-filled.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.config_parameter'].sudo().set_param('seeding_test_data.diag', '')
    seed_accounting_scaffold(env)
