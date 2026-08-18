# -*- coding: utf-8 -*-
{
    'name': 'Seeding - Test Data',
    'version': '17.0.0.0.12',
    # v0.0.11: force Fix-repair, BugFix-Sales, and
    # studio_usermodel_migration to load BEFORE this module. Without
    # those explicit deps, seeding_Test_data was loaded at position
    # 507/771 while its sister modules loaded later -- meaning their
    # x_studio_* fields on res.partner / helpdesk.stage weren't in
    # the model's `_fields` dict when the post-migration hook ran,
    # so the customer seeder silently dropped every Studio field.
    'depends': [
        'account', 'sale', 'stock', 'helpdesk',
        'Fix-repair',
        'BugFix-Sales',
        'studio_usermodel_migration',
    ],
    'summary': (
        'Seeds minimum accounting scaffold from Clear-DB reference '
        'onto the dev env so Repair automations can be tested E2E'
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
