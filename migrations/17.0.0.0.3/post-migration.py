# -*- coding: utf-8 -*-
"""v0.0.3 upgrade -- re-run the seed after fixing the company_ids bug.

v0.0.2 shipped with `company_ids: [(4, company.id)]` on account.account
creates. That's an invalid field on Odoo 17 (the model has plain
`company_id` m2o, not m2m). All 243 account creates were silently
swallowed by env.cr.savepoint(), then journal creation ran and Odoo
auto-created 15 dummy asset_cash accounts (one per bank/cash journal)
to satisfy their default_account_id constraint.

post_init_hook only runs on install, not on upgrade, so the fix in
hooks.py doesn't re-fire automatically. This migration script calls
the hook explicitly. The hook itself detects the partial-seed state
(15/243 accounts) and calls _reset_partial_seed to wipe the 15 dummies
and 49 journals before re-seeding from scratch.

Safe: _reset_partial_seed only touches records on the target company
(Jinasena Agricultural Machinery). No other companies affected.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_accounting_scaffold(env)
