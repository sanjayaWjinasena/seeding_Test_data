# -*- coding: utf-8 -*-
"""v0.0.9 upgrade -- diagnostic logging release.

v0.0.8's customer seed reached partner rows but every write silently
dropped its property + Studio values. Direct RPC writes on the same
partners work, so it's not an Odoo permission or field issue -- the
code path in the hook must be diverging. v0.0.9 adds targeted
_logger calls at every stage of _seed_customer_scaffold so the next
upgrade's log tells us exactly where things fall over.

Look for lines tagged 'seeding_test_data v0.0.9:' after upgrade.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_accounting_scaffold(env)
