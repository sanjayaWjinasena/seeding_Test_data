# -*- coding: utf-8 -*-
"""v0.0.4 upgrade -- add helpdesk team + members seed.

Snapshot from Clear-DB Company 2's "Customer Care - Repair" team:
  * privacy_visibility=internal (was portal on dev env -- caused the
    Helpdesk overview to not surface the team's kanban)
  * use_fsm=True, use_product_returns=True, use_sla=True
  * alias_name=customer-care-repair
  * member: kapila.h@jinasena.com.lk

Idempotent: matches an existing team on the target company by name
first, falls back to the first team on the company if the exact name
isn't present. Does NOT touch stage_ids -- Fix-repair owns stage
seeding, and touching stage_ids here would wipe the wiring.

post_init_hook only fires on install, so this migration script
explicitly re-fires the entry point.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_accounting_scaffold(env)
