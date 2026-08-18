# -*- coding: utf-8 -*-
"""v0.0.7 upgrade -- re-run the seed after fixing the accounting-
already-complete branch to also fire the customer seeder.

v0.0.6 had a bug: when accounts were already seeded (existing >=
expected), the hook did helpdesk + stage-reset then returned, never
calling _seed_customer_scaffold. Result on the initial v0.0.6
upgrade: partner count stayed at 148, no Clear-DB customers landed.

v0.0.7 fixes that branch (and the missing-JSON fallback branch too)
and re-fires the entry point so the 99 customers get created now.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_accounting_scaffold(env)
