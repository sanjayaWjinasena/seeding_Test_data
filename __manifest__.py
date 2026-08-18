# -*- coding: utf-8 -*-
{
    'name': 'Seeding - Test Data',
    'version': '17.0.0.0.14',
    # v0.0.14: customer seed lives in this module again. Testing
    # infrastructure should be reproducible via Apps -> Upgrade,
    # not an out-of-band script. The ir.property scope bug that
    # motivated the v0.0.13 removal is fixed by v0.0.12's
    # Partner.with_company(company) + OVERRIDE_KEYS combo.
    #
    # Load-order deps: without these three, res.partner._fields
    # wouldn't contain the x_studio_* fields at hook time (this
    # module gets loaded at ~507/771 in the graph; sisters load
    # later unless we depend on them).
    'depends': [
        'account', 'sale', 'stock', 'helpdesk',
        'Fix-repair',
        'BugFix-Sales',
        'studio_usermodel_migration',
    ],
    'summary': (
        'Seeds accounting scaffold + helpdesk team + repair stage '
        'company reset + 99 Jinasena AM customers with their '
        'property_* and Studio fields from the Clear-DB reference '
        'snapshot.'
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
