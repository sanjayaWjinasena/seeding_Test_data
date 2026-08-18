# -*- coding: utf-8 -*-
"""v0.0.5 upgrade -- clear x_studio_company_id on repair stages.

Fix-repair's Studio-ported ticket form view #7219 adds a stage_id
domain filter:

    [('team_ids', 'in', [team_id]), '|',
     ('x_studio_company_id', '=', company_id),
     ('x_studio_company_id', '=', False)]

If any of Fix-repair's 12 repair-pipeline stages has
x_studio_company_id set to Company 1 (the initial dev-env default),
that stage is excluded from the statusbar for every OTHER company --
Kapila (company 7 = Jinasena AM) only saw the 5 base helpdesk stages.

The Fix-repair XML seed intentionally leaves the field unset, but a
fresh Odoo install may have written Company 1 to it during system
initialization. This migration re-runs the hook so the stage-company
reset fires on existing dev envs.
"""
from odoo import api, SUPERUSER_ID

from odoo.addons.seeding_Test_data.hooks import seed_accounting_scaffold


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    seed_accounting_scaffold(env)
