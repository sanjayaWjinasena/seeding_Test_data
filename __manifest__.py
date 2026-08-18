# -*- coding: utf-8 -*-
{
    'name': 'Seeding - Test Data',
    'version': '17.0.0.0.13',
    # v0.0.13: scope reduced. Customer seeding moved to the standalone
    # scripts/import_customers_to_dev.py script (property_* fields are
    # ir.property, company-scoped, and don't write cleanly from a
    # post_init_hook running as SUPERUSER without an active company).
    #
    # Fix-repair stays as a dep because _reset_repair_stages_company
    # references helpdesk.stage.x_studio_company_id (declared by
    # Fix-repair v276+) and env.ref('Fix-repair.stage_*').
    'depends': [
        'account', 'sale', 'stock', 'helpdesk',
        'Fix-repair',
    ],
    'summary': (
        'Seeds minimum static reference data (accounting scaffold + '
        'helpdesk team + repair stage company reset) from Clear-DB '
        'reference. Customer data is loaded separately via '
        'scripts/import_customers_to_dev.py.'
    ),
    'author': 'Jinasena Agricultural Machinery (Pvt) Ltd.',
    'category': 'Accounting',
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
    ],
    'post_init_hook': 'seed_accounting_scaffold',
    'installable': True,
    'auto_install': False,
    'application': False,
}
