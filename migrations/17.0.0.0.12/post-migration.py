# -*- coding: utf-8 -*-
"""v0.0.12 upgrade -- fix property fields not writing.

v0.0.11 finally landed Studio fields on all 99 customers (with_group=98,
with_pm=98, with_vat=99) after the module-load-order fix. But property
fields still weren't writing:
    with_recv=2, with_term=1

Root cause: property_account_receivable_id, property_payment_term_id,
property_product_pricelist are Odoo ir.property fields -- their
storage is company-scoped. When the migration runs as SUPERUSER
without an active company in the env context, property writes go to
the wrong company scope (or the "global" scope). Reads against
company_id=7 then return False.

Two-part fix in hooks.py:
  1. Use Partner.with_company(company) for every partner search /
     create / write so property values land in the target company's
     scope.
  2. Add OVERRIDE_KEYS so property fields always take source-of-truth
     from the snapshot -- Odoo backfills a partner's pricelist to the
     env default at create-time, and the previous "only fill if
     empty" rule made every seeded pricelist look already-set and
     get skipped.

Re-fires the seed so the 99 customers get proper property values.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.config_parameter'].sudo().set_param('seeding_test_data.diag', '')
    seed_accounting_scaffold(env)
