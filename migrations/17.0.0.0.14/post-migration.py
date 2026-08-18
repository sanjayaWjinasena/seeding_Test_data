# -*- coding: utf-8 -*-
"""v0.0.14 upgrade -- restore customer seed inside the module.

v0.0.13 stripped customer seeding out and moved it to a standalone
script. Feedback from operation: testing infrastructure should be
reproducible via Apps -> Upgrade, not out-of-band. v0.0.14 restores
_seed_customer_scaffold using the v0.0.12 proven approach:

  * Partner.with_company(company) for every partner op so property_*
    (ir.property) writes land in the target company's scope.
  * OVERRIDE_KEYS force-writes the 5 property_* fields regardless
    of current DB value.

Also re-fires the entry point so the 99 customers get their
property + Studio fields on this upgrade.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.config_parameter'].sudo().set_param('seeding_test_data.diag', '')
    seed_accounting_scaffold(env)
