# -*- coding: utf-8 -*-
"""v0.0.10 upgrade -- diagnostics via ir.config_parameter.

ir.logging only records env['ir.logging'].create() calls, not
standard _logger.info() output. So v0.0.9's stdout logs weren't
readable via RPC. v0.0.10 writes each diagnostic step into
ir.config_parameter under key 'seeding_test_data.diag'. After the
upgrade we can RPC-read that key and see exactly what happened.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # Clear any prior diagnostic before re-firing.
    env['ir.config_parameter'].sudo().set_param('seeding_test_data.diag', '')
    seed_accounting_scaffold(env)
