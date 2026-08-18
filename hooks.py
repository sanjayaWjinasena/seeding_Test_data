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
HELPDESK_SEED_PATH = os.path.join(
    os.path.dirname(__file__), 'data', 'helpdesk_scaffold_seed.json'
)
# The source-of-truth company name (Clear-DB Company 2). We match by
# name against the dev env's res.company so the seed lands on the
# right legal entity regardless of ID differences.
TARGET_COMPANY_NAME = 'Jinasena Agricultural Machinery (Pvt) Ltd.'


def seed_accounting_scaffold(env):
    """Entry point registered as post_init_hook.

    v0.0.13: scope reduced to static reference data ONLY. Customer
    seeding was removed from this hook -- customer data (99 partners
    with property_* + Studio fields) is now imported by the
    standalone `scripts/import_customers_to_dev.py` script.

    Why: property_account_receivable_id / property_payment_term_id /
    property_product_pricelist are ir.property fields (company-
    scoped). Writing them from a post_init_hook (SUPERUSER, no
    active company) lands values in the wrong scope. An external
    script with explicit company context sidesteps that entire
    class of bug. Module hooks stay responsible for schema +
    minimal static reference data; the script owns real business
    data.

    What this hook still does:
      * Accounting scaffold (243 accounts + 49 journals)
      * Helpdesk team + members
      * Reset x_studio_company_id on repair-pipeline stages
    """
    Company = env['res.company'].sudo()
    company = Company.search([('name', '=', TARGET_COMPANY_NAME)], limit=1)
    if not company:
        _logger.warning(
            'seeding_test_data: no res.company named %r on this env '
            '-- skipping seed.',
            TARGET_COMPANY_NAME,
        )
        return
    if not os.path.isfile(SEED_PATH):
        _logger.warning(
            'seeding_test_data: accounting seed file missing at %s -- '
            'proceeding to helpdesk + stage reset',
            SEED_PATH,
        )
        _seed_helpdesk_scaffold(env, company)
        _reset_repair_stages_company(env)
        return
    with open(SEED_PATH, encoding='utf-8') as fh:
        snapshot = json.load(fh)

    existing = env['account.account'].sudo().search_count(
        [('company_id', '=', company.id)]
    )
    expected = len(snapshot.get('accounts', []))
    if existing >= expected:
        _logger.info(
            'seeding_test_data: company %s already has %d/%d accounts '
            '-- accounting seed complete, skipping to helpdesk.',
            company.name, existing, expected,
        )
        _seed_helpdesk_scaffold(env, company)
        _reset_repair_stages_company(env)
        return
    if existing:
        _logger.warning(
            'seeding_test_data: company %s has partial seed state '
            '(%d/%d accounts) -- resetting journals + accounts and '
            're-seeding from scratch. This deletes only records on '
            'the target company, no other companies affected.',
            company.name, existing, expected,
        )
        _reset_partial_seed(env, company)

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
    _seed_helpdesk_scaffold(env, company)
    _reset_repair_stages_company(env)
    _logger.info('seeding_test_data: seed complete on company %s', company.name)


def _reset_repair_stages_company(env):
    """v0.0.5: Fix-repair's Studio-ported ticket-form view #7219 adds
    a domain filter on stage_id:

        [('team_ids', 'in', [team_id]), '|',
         ('x_studio_company_id', '=', company_id),
         ('x_studio_company_id', '=', False)]

    If a repair-pipeline stage has x_studio_company_id set to Company 1
    (the initial 'My Company (San Francisco)' Odoo default), it's
    filtered out of the statusbar for every other company -- users see
    only the 5 base helpdesk stages.

    Fix-repair's data/repair_stages.xml intentionally leaves the field
    unset (defaults to False, matching for all companies). But on a
    fresh dev env, Odoo's install defaults may have set it to Company
    1. Clear it here so the widget shows all 12 repair stages.

    Idempotent: no-op when the stage's x_studio_company_id is already
    False (batch write short-circuits the actual DB update).
    """
    Stage = env['helpdesk.stage'].sudo()
    # Find the 12 Fix-repair repair-pipeline stages by their xmlid.
    # Use module='Fix-repair' + xml_id fragment so stages seeded by
    # data/repair_stages.xml are targeted; base helpdesk stages
    # (New, In Progress, ...) are untouched.
    if 'x_studio_company_id' not in Stage._fields:
        _logger.info(
            'seeding_test_data: helpdesk.stage.x_studio_company_id '
            'not declared -- skipping stage-company reset (Fix-repair '
            'v276+ required).'
        )
        return
    repair_stages = env.ref('Fix-repair.stage_sent_to_factory',
                            raise_if_not_found=False)
    xmlids = (
        'stage_sent_to_factory',
        'stage_received_at_factory',
        'stage_diagnosis',
        'stage_estimation_sent_to_customer',
        'stage_estimation_approval_received',
        'stage_advance_received',
        'stage_repair_started',
        'stage_repair_completed',
        'stage_sent_to_sales_centre',
        'stage_received_at_sales_centre',
        'stage_handed_over_to_customer',
        'stage_cancelled',
    )
    stages = Stage
    for xmlid in xmlids:
        rec = env.ref('Fix-repair.%s' % xmlid, raise_if_not_found=False)
        if rec:
            stages |= rec
    to_reset = stages.filtered(lambda s: s.x_studio_company_id)
    if to_reset:
        try:
            to_reset.write({'x_studio_company_id': False})
            _logger.info(
                'seeding_test_data: cleared x_studio_company_id on '
                '%d repair-pipeline stage(s)', len(to_reset),
            )
        except Exception as e:
            _logger.warning(
                'seeding_test_data: stage-company reset failed -- %s', e,
            )
    else:
        _logger.info(
            'seeding_test_data: no repair-pipeline stages need '
            'x_studio_company_id reset (idempotent skip).'
        )


def _seed_helpdesk_scaffold(env, company):
    """v0.0.4: snapshot Clear-DB's Customer Care - Repair team config
    (privacy=internal, use_fsm=True, use_product_returns=True, etc.)
    + member list onto the target company's helpdesk.team.

    Idempotent by team name -- updates an existing team if found,
    creates one otherwise. Does not touch stage_ids (Fix-repair
    owns stage seeding).
    """
    if not os.path.isfile(HELPDESK_SEED_PATH):
        _logger.info(
            'seeding_test_data: helpdesk seed file not present -- skipping'
        )
        return
    if 'helpdesk.team' not in env.registry:
        _logger.info(
            'seeding_test_data: helpdesk module not installed -- skipping team seed'
        )
        return
    with open(HELPDESK_SEED_PATH, encoding='utf-8') as fh:
        snapshot = json.load(fh)

    Team = env['helpdesk.team'].sudo()
    Users = env['res.users'].sudo()
    for team_row in snapshot.get('teams') or []:
        with env.cr.savepoint():
            try:
                # Locate existing team on this company by name first;
                # fall back to any team on this company if the exact
                # name isn't present (dev-env teams may be pre-existing
                # under a different name like plain "Customer Care").
                target = Team.search([
                    ('company_id', '=', company.id),
                    ('name', '=', team_row['name']),
                ], limit=1)
                if not target:
                    target = Team.search([
                        ('company_id', '=', company.id),
                    ], limit=1)
                # Resolve member logins to user ids on this env.
                member_ids = []
                for login in team_row.get('member_logins') or []:
                    u = Users.search([('login', '=', login)], limit=1)
                    if u:
                        member_ids.append(u.id)
                # Fields safe to write on both create and update.
                # `stage_ids` intentionally omitted -- Fix-repair owns
                # stage seeding, and touching it here would wipe the
                # existing wire-up.
                writable = {
                    'sequence', 'active', 'privacy_visibility',
                    'auto_assignment', 'assign_method',
                    'use_alias', 'alias_name',
                    'use_website_helpdesk_form',
                    'use_helpdesk_timesheet',
                    'use_helpdesk_sale_timesheet',
                    'use_credit_notes', 'use_product_returns',
                    'use_product_repairs', 'use_fsm',
                    'use_rating', 'use_sla', 'description',
                }
                vals = {k: v for k, v in team_row.items()
                        if k in writable and v is not None}
                if member_ids:
                    vals['member_ids'] = [(6, 0, member_ids)]
                if target:
                    # Rename only if the existing team is a plain default.
                    if target.name != team_row['name'] \
                            and target.name in ('Customer Care', 'Helpdesk'):
                        vals['name'] = team_row['name']
                    target.write(vals)
                    _logger.info(
                        'seeding_test_data: updated helpdesk.team %r on %s '
                        '(members=%d)',
                        target.name, company.name, len(member_ids),
                    )
                else:
                    vals['name'] = team_row['name']
                    vals['company_id'] = company.id
                    Team.create(vals)
                    _logger.info(
                        'seeding_test_data: created helpdesk.team %r on %s '
                        '(members=%d)',
                        team_row['name'], company.name, len(member_ids),
                    )
            except Exception as e:
                _logger.warning(
                    'seeding_test_data: helpdesk team %r seed failed -- %s',
                    team_row.get('name'), e,
                )


def _reset_partial_seed(env, company):
    """Remove auto-created journals + accounts left over from a failed
    prior seed. Only touches records on the target company."""
    Journal = env['account.journal'].sudo()
    Account = env['account.account'].sudo()
    journals = Journal.search([('company_id', '=', company.id)])
    if journals:
        # Journals must be unlinked before their default_account_id
        # accounts, otherwise Odoo raises a foreign-key protection.
        try:
            journals.unlink()
            _logger.info(
                'seeding_test_data: deleted %d journals on %s',
                len(journals), company.name,
            )
        except Exception as e:
            _logger.warning(
                'seeding_test_data: could not delete journals on %s -- %s',
                company.name, e,
            )
    accounts = Account.search([('company_id', '=', company.id)])
    if accounts:
        try:
            accounts.unlink()
            _logger.info(
                'seeding_test_data: deleted %d accounts on %s',
                len(accounts), company.name,
            )
        except Exception as e:
            _logger.warning(
                'seeding_test_data: could not delete accounts on %s -- %s',
                company.name, e,
            )


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
                # Odoo 17: account.account carries a plain company_id
                # (m2o), not company_ids (m2m). The v0.0.2 bug used
                # company_ids and silently failed all 243 creates.
                vals = {
                    'name': row['name'],
                    'code': code,
                    'account_type': row['account_type'],
                    'reconcile': bool(row.get('reconcile')),
                    'company_id': company.id,
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
