# -*- coding: utf-8 -*-
"""v0.0.6 upgrade -- seed 99 Jinasena AM customers + payment terms +
pricelists from Clear-DB.

Requires BugFix-Sales v46 for the 4 product.pricelist Studio fields.
Studio-usermodel-migration v0.0.4 already seeded x_customer_group data
that's referenced by the customer x_studio_customer_group m2o.

Match strategy: skip existing partners by name. Payment terms and
pricelists are also match-by-name so re-runs don't create duplicates.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_accounting_scaffold(env)
