# -*- coding: utf-8 -*-
"""v0.0.13 upgrade -- module scope reduced.

Customer seeding was removed from the post-init hook (see hooks.py
docstring and the module's __manifest__ for rationale). Customer
data now flows through scripts/import_customers_to_dev.py, which
runs outside the Odoo install path with explicit company context so
ir.property fields land in the right scope.

This migration:
  * Clears the seeding_test_data.diag ir.config_parameter left over
    from v0.0.10-0.12 diagnostics.
  * Re-fires the entry point so accounting + helpdesk + stage-reset
    still run under the new (smaller) surface.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.config_parameter'].sudo().set_param('seeding_test_data.diag', '')
    seed_accounting_scaffold(env)
