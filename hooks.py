# -*- coding: utf-8 -*-
"""seeding_test_data -- post_init_hook.

Reads data/accounting_scaffold_seed.json (243 accounts + 49 journals
snapshotted from Clear-DB Company 2 "Jinasena Agricultural Machinery
(Pvt) Ltd.") and creates equivalent rows on the dev env's company
matching by name.

Rationale: dev env has zero accounting scaffold on any of its 8
companies, so no invoice / payment E2E test is possible. Installing
Sri Lanka's l10n_lk isn't an option here (module isn't shipped on this
Odoo image). This seed builds enough scaffold to post invoices +
register payments for Repair-workflow automation tests without
touching Clear-DB.

Safety:
  * Only seeds if the target company currently has 0 accounts (won't
    clobber an existing CoA).
  * Uses env.cr.savepoint() per section so partial failures don't
    poison the transaction.
  * Uses code-based lookups when creating journals (default_account_id
    resolves against the newly-created accounts by code).
"""
import json
import logging
import os

_logger = logging.getLogger(__name__)


SEED_PATH = os.path.join(
    os.path.dirname(__file__), 'data', 'accounting_scaffold_seed.json'
)
# The source-of-truth company name (Clear-DB Company 2). We match by
# name against the dev env's res.company so the seed lands on the
# right legal entity regardless of ID differences.
TARGET_COMPANY_NAME = 'Jinasena Agricultural Machinery (Pvt) Ltd.'


def seed_accounting_scaffold(env):
    """Entry point registered as post_init_hook."""
    if not os.path.isfile(SEED_PATH):
        _logger.warning(
            'seeding_test_data: seed file not found at %s -- skipping',
            SEED_PATH,
        )
        return
    with open(SEED_PATH, encoding='utf-8') as fh:
        snapshot = json.load(fh)

    Company = env['res.company'].sudo()
    company = Company.search([('name', '=', TARGET_COMPANY_NAME)], limit=1)
    if not company:
        _logger.warning(
            'seeding_test_data: no res.company named %r on this env '
            '-- skipping seed. Rename a company or edit '
            'TARGET_COMPANY_NAME in hooks.py.',
            TARGET_COMPANY_NAME,
        )
        return

    existing = env['account.account'].sudo().search_count(
        [('company_id', '=', company.id)]
    )
    if existing:
        _logger.info(
            'seeding_test_data: company %s already has %d accounts -- '
            'skipping seed (would clobber existing CoA)',
            company.name, existing,
        )
        return

    _logger.info(
        'seeding_test_data: seeding accounting scaffold on %s -- '
        '%d accounts + %d journals from Clear-DB reference',
        company.name,
        len(snapshot.get('accounts', [])),
        len(snapshot.get('journals', [])),
    )

    code_to_account_id = _create_accounts(env, company, snapshot['accounts'])
    _create_journals(env, company, snapshot['journals'], code_to_account_id)
    _set_company_defaults(
        env, company, snapshot.get('company_defaults') or {}, code_to_account_id
    )
    _logger.info('seeding_test_data: seed complete on company %s', company.name)


def _create_accounts(env, company, accounts):
    """Create account.account rows. Return code->id map."""
    Account = env['account.account'].sudo()
    code_to_id = {}
    for row in accounts:
        code = row.get('code')
        if not code:
            continue
        with env.cr.savepoint():
            try:
                vals = {
                    'name': row['name'],
                    'code': code,
                    'account_type': row['account_type'],
                    'reconcile': bool(row.get('reconcile')),
                    'company_ids': [(4, company.id)],
                }
                # currency_id is [id, name] or False
                cur = row.get('currency_id')
                if isinstance(cur, list):
                    # Resolve by name to a currency existing on this env.
                    curr = env['res.currency'].search(
                        [('name', '=', cur[1])], limit=1
                    )
                    if curr:
                        vals['currency_id'] = curr.id
                acc = Account.create(vals)
                code_to_id[code] = acc.id
            except Exception as e:
                _logger.warning(
                    'seeding_test_data: skip account %s (%s) -- %s',
                    code, row.get('name'), e,
                )
    _logger.info('seeding_test_data: created %d accounts', len(code_to_id))
    return code_to_id


def _create_journals(env, company, journals, code_to_account_id):
    """Create account.journal rows. default_account_id resolved by code."""
    Journal = env['account.journal'].sudo()

    def _resolve_account_ref(ref):
        """ref is [id, "<code> <name>"] or False. Return account id
        on the target env by parsing code out of the label."""
        if not isinstance(ref, list) or len(ref) < 2:
            return False
        label = ref[1] or ''
        # Label format on Clear-DB is "<code> <name>" (space-separated).
        # Split once on first space to isolate code.
        parts = label.split(' ', 1)
        if not parts:
            return False
        code = parts[0]
        return code_to_account_id.get(code, False)

    created = 0
    for row in journals:
        code = row.get('code')
        if not code:
            continue
        with env.cr.savepoint():
            try:
                vals = {
                    'name': row['name'],
                    'code': code,
                    'type': row['type'],
                    'company_id': company.id,
                }
                default_id = _resolve_account_ref(row.get('default_account_id'))
                if default_id:
                    vals['default_account_id'] = default_id
                susp_id = _resolve_account_ref(row.get('suspense_account_id'))
                if susp_id:
                    vals['suspense_account_id'] = susp_id
                Journal.create(vals)
                created += 1
            except Exception as e:
                _logger.warning(
                    'seeding_test_data: skip journal %s (%s) -- %s',
                    code, row.get('name'), e,
                )
    _logger.info('seeding_test_data: created %d journals', created)


def _set_company_defaults(env, company, defaults, code_to_account_id):
    """Fill in res.company account defaults from the snapshot."""
    if not defaults:
        return

    def _resolve(ref):
        if not isinstance(ref, list) or len(ref) < 2:
            return False
        code = (ref[1] or '').split(' ', 1)[0]
        return code_to_account_id.get(code, False)

    field_map = {
        'account_journal_suspense_account_id':
            defaults.get('account_journal_suspense_account_id'),
        'account_journal_payment_debit_account_id':
            defaults.get('account_journal_payment_debit_account_id'),
        'account_journal_payment_credit_account_id':
            defaults.get('account_journal_payment_credit_account_id'),
        'account_journal_early_pay_discount_gain_account_id':
            defaults.get('account_journal_early_pay_discount_gain_account_id'),
        'account_journal_early_pay_discount_loss_account_id':
            defaults.get('account_journal_early_pay_discount_loss_account_id'),
        'expense_currency_exchange_account_id':
            defaults.get('expense_currency_exchange_account_id'),
        'income_currency_exchange_account_id':
            defaults.get('income_currency_exchange_account_id'),
        'transfer_account_id':
            defaults.get('transfer_account_id'),
    }
    payload = {}
    for field, ref in field_map.items():
        resolved = _resolve(ref)
        if resolved:
            payload[field] = resolved
    if payload:
        with env.cr.savepoint():
            try:
                company.write(payload)
                _logger.info(
                    'seeding_test_data: wrote %d company defaults on %s',
                    len(payload), company.name,
                )
            except Exception as e:
                _logger.warning(
                    'seeding_test_data: company defaults write failed -- %s', e,
                )
