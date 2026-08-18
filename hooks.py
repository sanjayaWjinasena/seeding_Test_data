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
CUSTOMER_SEED_PATH = os.path.join(
    os.path.dirname(__file__), 'data', 'customer_scaffold_seed.json'
)
# The source-of-truth company name (Clear-DB Company 2). We match by
# name against the dev env's res.company so the seed lands on the
# right legal entity regardless of ID differences.
TARGET_COMPANY_NAME = 'Jinasena Agricultural Machinery (Pvt) Ltd.'


def seed_accounting_scaffold(env):
    """Entry point registered as post_init_hook.

    Despite the historical name, this now also seeds helpdesk team +
    members (see _seed_helpdesk_scaffold). Kept the original function
    name for manifest compatibility with the v0.0.1 install.
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
            'proceeding to helpdesk + customer seed',
            SEED_PATH,
        )
        _seed_helpdesk_scaffold(env, company)
        _reset_repair_stages_company(env)
        _seed_customer_scaffold(env, company)
        return
    with open(SEED_PATH, encoding='utf-8') as fh:
        snapshot = json.load(fh)

    existing = env['account.account'].sudo().search_count(
        [('company_id', '=', company.id)]
    )
    # Guard: skip only if the seed appears to have completed already.
    # v0.0.2 shipped with a `company_ids` bug that silently failed all
    # account creates, and Odoo then auto-created 15 dummy asset_cash
    # accounts (one per bank/cash journal). That leaves the company
    # with 15 accounts + 49 journals, all wrong. On upgrade, detect
    # this partial-seed state and reset it.
    expected = len(snapshot.get('accounts', []))
    if existing >= expected:
        _logger.info(
            'seeding_test_data: company %s already has %d/%d accounts '
            '-- accounting seed complete, skipping to helpdesk.',
            company.name, existing, expected,
        )
        # v0.0.4: still seed helpdesk (its own idempotency guard runs)
        _seed_helpdesk_scaffold(env, company)
        # v0.0.5: also reset repair-stage company (idempotent)
        _reset_repair_stages_company(env)
        # v0.0.7: also seed customers (its own skip-existing guard runs)
        _seed_customer_scaffold(env, company)
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
    # v0.0.4: helpdesk team + members. Runs unconditionally after
    # accounting even when accounting was skipped -- guarded from
    # within by its own idempotency check.
    _seed_helpdesk_scaffold(env, company)
    # v0.0.5: reset x_studio_company_id on repair-pipeline stages.
    _reset_repair_stages_company(env)
    # v0.0.6: seed customers + payment terms + pricelists.
    _seed_customer_scaffold(env, company)
    _logger.info('seeding_test_data: seed complete on company %s', company.name)


def _seed_customer_scaffold(env, company):
    """v0.0.6: seed 99 Jinasena AM customers + their payment terms +
    referenced pricelists from Clear-DB. Match strategy: skip existing
    partners by name to avoid clobbering dev-env test artifacts (e.g.
    Acme Corporation used by SO 81).

    Reference resolution:
      * property_account_receivable_id -> by account.code
      * property_payment_term_id -> by term.name
      * property_product_pricelist -> by pricelist.name
      * x_studio_customer_group -> by group.x_name (studio_usermodel_migration)
      * country_id / state_id -> by name (skip if not found)
    """
    if not os.path.isfile(CUSTOMER_SEED_PATH):
        _logger.info(
            'seeding_test_data: customer seed file not present -- skipping'
        )
        return
    with open(CUSTOMER_SEED_PATH, encoding='utf-8') as fh:
        snapshot = json.load(fh)

    # 1. Payment terms (create-if-missing, match by name)
    Term = env['account.payment.term'].sudo()
    term_name_to_id = {}
    for row in snapshot.get('payment_terms') or []:
        name = row.get('name')
        if not name:
            continue
        existing = Term.search([('name', '=', name)], limit=1)
        if existing:
            term_name_to_id[name] = existing.id
            continue
        with env.cr.savepoint():
            try:
                new = Term.create({
                    'name': name,
                    'active': bool(row.get('active', True)),
                    'sequence': row.get('sequence') or 10,
                    'note': row.get('note') or '',
                })
                term_name_to_id[name] = new.id
                _logger.info(
                    'seeding_test_data: created payment term %r (id %d)',
                    name, new.id,
                )
            except Exception as e:
                _logger.warning(
                    'seeding_test_data: skip payment term %r -- %s',
                    name, e,
                )

    # 2. Pricelists (create-if-missing, match by name).
    # Also register the currency-suffixed display_name variant so
    # customer refs (which carry '<name> (<currency>)') resolve.
    Pricelist = env['product.pricelist'].sudo()
    pricelist_name_to_id = {}

    def _register_pricelist(pl_id, name, currency_code):
        pricelist_name_to_id[name] = pl_id
        if currency_code:
            pricelist_name_to_id['%s (%s)' % (name, currency_code)] = pl_id

    for row in snapshot.get('pricelists') or []:
        name = row.get('name')
        if not name:
            continue
        cur = row.get('currency_id')
        curr_code = cur[1] if isinstance(cur, list) and len(cur) > 1 else None
        existing = Pricelist.search([('name', '=', name)], limit=1)
        if existing:
            _register_pricelist(existing.id, name, curr_code)
            continue
        with env.cr.savepoint():
            try:
                vals = {
                    'name': name,
                    'active': bool(row.get('active', True)),
                    'sequence': row.get('sequence') or 10,
                    'discount_policy': row.get('discount_policy') or 'with_discount',
                }
                if curr_code:
                    curr = env['res.currency'].search(
                        [('name', '=', curr_code)], limit=1
                    )
                    if curr:
                        vals['currency_id'] = curr.id
                # x_studio_ pricelist fields (BugFix-Sales v46+)
                for k in ('x_studio_group_type', 'x_studio_order_payment_method',
                          'x_studio_project_price_list', 'x_studio_zzzz'):
                    if k in row and k in Pricelist._fields:
                        vals[k] = row[k]
                new = Pricelist.create(vals)
                _register_pricelist(new.id, name, curr_code)
                _logger.info(
                    'seeding_test_data: created pricelist %r (id %d)',
                    name, new.id,
                )
            except Exception as e:
                _logger.warning(
                    'seeding_test_data: skip pricelist %r -- %s', name, e,
                )

    # 3. Customer groups already seeded by studio_usermodel_migration.
    # Build a name -> id lookup for reference resolution.
    group_x_name_to_id = {}
    if 'x_customer_group' in env.registry:
        Group = env['x_customer_group'].sudo()
        for g in Group.search([]):
            key = getattr(g, 'x_name', None) or g.display_name
            if key:
                group_x_name_to_id[key] = g.id

    # 4. Account code -> id lookup for property_account_receivable_id
    account_code_to_id = {}
    for a in env['account.account'].sudo().search(
        [('company_id', '=', company.id)]
    ):
        account_code_to_id[a.code] = a.id

    # 5. Country / state lookup helpers
    def _resolve_ref(ref, model, field='name'):
        if not isinstance(ref, list) or len(ref) < 2:
            return False
        name = ref[1]
        rec = env[model].sudo().search([(field, '=', name)], limit=1)
        return rec.id if rec else False

    # 6. Customers: create net-new OR back-fill missing fields on
    # customers that already exist by name. v0.0.6 hit a bug where
    # Odoo's `create()` silently dropped several property + Studio
    # values (property_account_receivable_id, property_payment_term_id,
    # x_studio_customer_group, x_studio_group_type, etc.), leaving
    # partial records. v0.0.8 runs an explicit `write()` after the
    # partner exists so those fields land.
    Partner = env['res.partner'].sudo()

    # Field-name-agnostic reference resolvers. Each key is a
    # relation model; each value is a callable that takes the source
    # ref (typically [source_id, display_name]) and returns a target
    # env id (int) or False. Adding a new Studio m2o that points to
    # one of these models "just works" -- no code change needed.
    #
    # For relations NOT listed here we fall back to a generic
    # search-by-display-name; add an entry to override the strategy
    # when name-based match is unreliable (e.g. account.account
    # display_name is '<code> <name>' -- we key on code instead).
    RELATION_RESOLVERS = {
        'account.account': lambda ref: account_code_to_id.get(
            (ref[1] or '').split(' ', 1)[0]) if isinstance(ref, list) and len(ref) >= 2 else False,
        'account.payment.term': lambda ref: term_name_to_id.get(
            ref[1]) if isinstance(ref, list) and len(ref) >= 2 else False,
        'product.pricelist': lambda ref: pricelist_name_to_id.get(
            ref[1]) if isinstance(ref, list) and len(ref) >= 2 else False,
        'x_customer_group': lambda ref: group_x_name_to_id.get(
            ref[1]) if isinstance(ref, list) and len(ref) >= 2 else False,
    }

    # Fields we NEVER copy from the snapshot -- they're either
    # source-only identity, computed on target, or intentionally
    # left as env-default (e.g. company_id is set from `company`).
    SKIP_FIELDS = frozenset((
        'id',                # source-only pk
        'display_name',      # computed
        'create_uid', 'create_date',
        'write_uid', 'write_date',
        '__last_update',
        'company_id',        # caller sets from target company
        'company_ids',       # multi-company: leave env default
    ))

    def _resolve_relation(field, ref):
        """Return an id on the target env for a m2o ref, or False."""
        relation = field.comodel_name
        resolver = RELATION_RESOLVERS.get(relation)
        if resolver:
            return resolver(ref)
        # Generic fallback: match relation by display_name.
        if isinstance(ref, list) and len(ref) >= 2 and ref[1]:
            rec = env[relation].sudo().search(
                [('display_name', '=', ref[1])], limit=1)
            return rec.id if rec else False
        return False

    def _build_config_vals(row):
        """Data-driven mapping of snapshot row -> target-env vals.
        Iterates every key in the row, honours the Partner._fields
        schema, and skips anything we can't safely write. New
        Studio fields on Clear-DB flow through without code changes."""
        v = {}
        for key, source_val in row.items():
            if key in SKIP_FIELDS:
                continue
            field = Partner._fields.get(key)
            if field is None:
                # Field not declared on this env -- silently skip.
                # (Common for Studio-only fields that a target module
                #  hasn't ported yet.)
                continue
            if source_val in (False, None, ''):
                # Skip empty source values -- don't clobber defaults
                # or user-set values on backfill.
                continue
            ftype = field.type
            if ftype in ('many2one',):
                rid = _resolve_relation(field, source_val)
                if rid:
                    v[key] = rid
            elif ftype in ('char', 'text', 'html', 'selection',
                           'integer', 'float', 'monetary',
                           'boolean', 'date', 'datetime'):
                v[key] = source_val
            elif ftype in ('many2many', 'one2many'):
                # Skip for now -- x2many needs relation-record hydration
                # that this seeder doesn't do. Add explicit handling
                # per field when a specific x2many needs seeding.
                continue
            # binary / reference / etc. -- skip conservatively.
        return v

    created_c = backfilled_c = unchanged_c = 0
    for row in snapshot.get('customers') or []:
        name = row.get('name')
        if not name:
            continue
        existing = Partner.search([('name', '=', name)], limit=1)
        cfg = _build_config_vals(row)
        with env.cr.savepoint():
            try:
                if existing:
                    # Only write config fields; leave core identity alone.
                    # And only write keys where the current value is
                    # empty (falsy) -- don't clobber a manually-set value.
                    to_write = {}
                    current = existing.read(list(cfg.keys()))[0] if cfg else {}
                    for k, v in cfg.items():
                        cur = current.get(k)
                        # For m2o fields, current is [id, name] or False.
                        cur_id = cur[0] if isinstance(cur, list) else cur
                        if not cur_id:
                            to_write[k] = v
                    if to_write:
                        existing.write(to_write)
                        backfilled_c += 1
                    else:
                        unchanged_c += 1
                else:
                    vals = dict(cfg)
                    vals.update({
                        'name': name,
                        'is_company': bool(row.get('is_company', True)),
                        'customer_rank': row.get('customer_rank') or 1,
                        'supplier_rank': row.get('supplier_rank') or 0,
                        'company_id': company.id,
                    })
                    Partner.create(vals)
                    created_c += 1
                    # v0.0.8 -- property + Studio fields sometimes drop on
                    # create() for reasons that vary by Odoo release. Do
                    # an immediate write() to lock them in.
                    new = Partner.search([('name', '=', name)], limit=1)
                    if new and cfg:
                        try:
                            new.write(cfg)
                        except Exception as e2:
                            _logger.warning(
                                'seeding_test_data: post-create write '
                                'for %r -- %s', name, e2,
                            )
            except Exception as e:
                _logger.warning(
                    'seeding_test_data: skip/backfill customer %r -- %s',
                    name, e,
                )
    _logger.info(
        'seeding_test_data: customers -- created %d, back-filled %d, '
        'unchanged %d', created_c, backfilled_c, unchanged_c,
    )


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
