# -*- coding: utf-8 -*-
"""v0.0.8 upgrade -- customer seeder rewritten data-driven + backfill.

Two problems on v0.0.7 seeded customers:
  1. `property_product_pricelist` lookup missed because Clear-DB's
     customer ref carried the currency-suffixed display_name
     ('JAM General Pricelist (LKR)'), while our pricelist map keyed
     by the raw `name` field ('JAM General Pricelist'). Fix: register
     both variants in the map.
  2. `property_account_receivable_id`, `property_payment_term_id`,
     `x_studio_customer_group`, and every x_studio_* value on the
     customer stayed False because Odoo's `create()` silently
     dropped several of them (pattern varies by Odoo release).
     Fix: follow up create() with an explicit write() of the same
     config vals -- redundant on happy path, but idempotent, and
     locks in any field that create() didn't accept.

Also refactored the customer loop to be fully data-driven: iterates
every key in the snapshot row, honours Partner._fields metadata,
and dispatches based on field.type. Adding new Studio fields on
Clear-DB no longer requires editing this hook -- as long as the
field is declared on the target env's res.partner, it flows through
automatically.

This migration re-fires the entry point so the 99 already-seeded
customers get their missing config values back-filled.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_accounting_scaffold(env)
