# Copyright 2026 STARK LABS
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging
import re

from werkzeug.urls import url_join

from odoo import _
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.tools import email_normalize_all
from odoo.tools.misc import consteq

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_tilopay import const

_logger = logging.getLogger(__name__)


def split_name(full_name):
    parts = (full_name or '').split()
    if len(parts) > 1:
        return parts[0], parts[-1]
    if parts:
        return parts[0], parts[0]
    return '', ''


def parse_int(value):
    if not value and value != 0:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def resolve_sale_order_id(env, sale_order_id=None):
    """Resolve a sale order id from portal or payment-link context."""
    for candidate in (
        sale_order_id,
        env.context.get('sale_order_id'),
    ):
        parsed = parse_int(candidate)
        if parsed:
            return parsed

    httprequest = getattr(request, 'httprequest', None)
    if httprequest:
        parsed = parse_int(httprequest.args.get('sale_order_id'))
        if parsed:
            return parsed
        path_match = re.search(r'/my/orders/(\d+)', httprequest.path or '')
        if path_match:
            return int(path_match.group(1))

    try:
        parsed = parse_int((getattr(request, 'params', None) or {}).get('sale_order_id'))
        if parsed:
            return parsed
    except RuntimeError:
        pass

    session = getattr(request, 'session', None)
    if session:
        parsed = parse_int(session.get('sale_order_id'))
        if parsed:
            return parsed
    return None


def get_sale_order_sudo(
    env,
    order_id,
    access_token=None,
    partner_id=None,
    amount=None,
    currency_id=None,
):
    """Return a sale order using sudo after validating portal or payment access."""
    order_sudo = env['sale.order'].sudo().browse(order_id).exists()
    if not order_sudo:
        raise MissingError(_('This document does not exist.'))
    if access_token and order_sudo.access_token and consteq(order_sudo.access_token, access_token):
        return order_sudo
    if partner_id is not None and amount is not None and currency_id is not None:
        if payment_utils.check_access_token(
            access_token, partner_id, float(amount), int(currency_id),
        ):
            return order_sudo
    if not env.user._is_public() and order_sudo.partner_id.commercial_partner_id == env.user.partner_id.commercial_partner_id:
        return order_sudo
    raise AccessError(_('You are not allowed to access this document.'))


def get_transaction_sudo(
    env,
    reference,
    access_token=None,
    partner_id=None,
    amount=None,
    currency_id=None,
    sale_order_id=None,
):
    """Return a Tilopay transaction after validating portal or payment access."""
    tx_sudo = env['payment.transaction'].sudo().search([
        ('reference', '=', reference),
        ('provider_code', '=', 'tilopay'),
    ], limit=1)
    if not tx_sudo:
        raise MissingError(_('This payment transaction does not exist.'))
    if partner_id is not None and tx_sudo.partner_id.id != int(partner_id):
        raise AccessError(_('You are not allowed to access this payment transaction.'))
    if amount is not None and currency_id is not None:
        currency = env['res.currency'].sudo().browse(int(currency_id))
        if currency and tx_sudo.currency_id.compare_amounts(tx_sudo.amount, float(amount)) != 0:
            raise AccessError(_('You are not allowed to access this payment transaction.'))
    if sale_order_id:
        get_sale_order_sudo(
            env,
            sale_order_id,
            access_token=access_token,
            partner_id=partner_id,
            amount=amount,
            currency_id=currency_id,
        )
        return tx_sudo
    if access_token and partner_id is not None and amount is not None and currency_id is not None:
        if payment_utils.check_access_token(
            access_token, partner_id, float(amount), int(currency_id),
        ):
            return tx_sudo
    if not env.user._is_public() and tx_sudo.partner_id.commercial_partner_id == env.user.partner_id.commercial_partner_id:
        return tx_sudo
    raise AccessError(_('You are not allowed to access this payment transaction.'))


def _state_for_tilopay(state_record, city=''):
    """Return a human-readable state/province label for Tilopay."""
    if state_record:
        name = (state_record.name or '').strip()
        if name:
            return name
        code = (state_record.code or '').strip()
        if code and '-' in code:
            return code.split('-', 1)[1]
        return code
    return (city or '').strip()


def _normalize_telephone(phone):
    """Return digits-only phone with at least 8 digits for Tilopay."""
    digits = re.sub(r'\D', '', phone or '')
    if len(digits) >= 8:
        return digits[:15]
    return const.SDK_BILLING_DEFAULTS['billToTelephone']


def get_redirect_url(provider):
    """Return the public callback URL sent to Tilopay."""
    custom_url = (provider.tilopay_return_url or '').strip()
    if custom_url:
        return custom_url
    base_url = provider.get_base_url()
    if not base_url:
        raise UserError(_('Configure the system parameter web.base.url before taking payments.'))
    return url_join(base_url, const.RETURN_URL)


def document_reference(transaction):
    """Return the payment transaction reference as Tilopay orderNumber.

    Tilopay requires a unique orderNumber per payment attempt; Odoo transaction
    references (e.g. S00137-2) must be used instead of the sale order name.
    """
    transaction.ensure_one()
    return transaction.sudo().reference


def _billing_from_partner(partner):
    partner = partner.with_context(show_address=1)
    commercial = partner.commercial_partner_id
    partner_name = (partner.name or commercial.name or '').strip()
    first_name, last_name = split_name(partner_name)

    return {
        'billToFirstName': first_name,
        'billToLastName': last_name,
        'billToAddress': (partner.street or commercial.street or '').strip(),
        'billToAddress2': (partner.street2 or commercial.street2 or '').strip(),
        'billToCity': (partner.city or commercial.city or '').strip(),
        'billToState': _state_for_tilopay(
            partner.state_id or commercial.state_id,
            city=(partner.city or commercial.city or ''),
        ),
        'billToZipPostCode': (partner.zip or commercial.zip or '').strip(),
        'billToCountry': (
            partner.country_id.code if partner.country_id
            else commercial.country_id.code if commercial.country_id else ''
        ),
        'billToEmail': (email_normalize_all(partner.email or '') or [''])[0],
        'billToTelephone': _normalize_telephone(
            partner.phone or partner.mobile or commercial.phone or commercial.mobile or '',
        ),
    }


def _billing_from_transaction(transaction):
    transaction = transaction.sudo()
    partner = transaction.partner_id.with_context(show_address=1)
    partner_name = (transaction.partner_name or partner.name or '').strip()
    first_name, last_name = split_name(partner_name)

    return {
        'billToFirstName': first_name,
        'billToLastName': last_name,
        'billToAddress': (transaction.partner_address or partner.street or '').strip(),
        'billToAddress2': (partner.street2 or '').strip(),
        'billToCity': (transaction.partner_city or partner.city or '').strip(),
        'billToState': _state_for_tilopay(
            transaction.partner_state_id or partner.state_id,
            city=(transaction.partner_city or partner.city or ''),
        ),
        'billToZipPostCode': (transaction.partner_zip or partner.zip or '').strip(),
        'billToCountry': (
            transaction.partner_country_id.code if transaction.partner_country_id
            else partner.country_id.code if partner.country_id else ''
        ),
        'billToEmail': (
            email_normalize_all(transaction.partner_email or partner.email or '') or ['']
        )[0],
        'billToTelephone': _normalize_telephone(
            transaction.partner_phone or partner.phone or partner.mobile or '',
        ),
    }


def _apply_sdk_billing_defaults(billing, partner=None, env=None):
    """Fill empty billing fields required by Tilopay SDK validate() and the payment API."""
    name_fallback = (
        billing.get('billToFirstName')
        or billing.get('billToLastName')
        or (partner.name if partner else None)
        or 'Customer'
    )
    if not billing.get('billToFirstName'):
        billing['billToFirstName'] = name_fallback
    if not billing.get('billToLastName'):
        billing['billToLastName'] = billing['billToFirstName']
    if not billing.get('billToAddress'):
        billing['billToAddress'] = '-'
    if not billing.get('billToCountry'):
        country = None
        if partner:
            country = partner.country_id or partner.commercial_partner_id.country_id
        if not country and env:
            country = env.company.country_id
        billing['billToCountry'] = country.code if country else 'XX'

    for field_name, default in const.SDK_BILLING_DEFAULTS.items():
        if not billing.get(field_name):
            billing[field_name] = default

    billing['billToTelephone'] = _normalize_telephone(billing.get('billToTelephone'))
    if not billing.get('billToState'):
        billing['billToState'] = billing.get('billToCity') or const.SDK_BILLING_DEFAULTS['billToState']
    return billing


def prepare_billing_fields(partner, order_number, transaction=None, env=None):
    """Build Tilopay billTo* fields for Tilopay.Init().

    Per Tilopay SDK documentation, only billToEmail and orderNumber are mandatory
    at Init time. The SDK validate() step before payment also requires non-empty
    billToFirstName, billToLastName, billToAddress, and billToCountry.
    """
    billing = _billing_from_transaction(transaction) if transaction else _billing_from_partner(partner)
    billing['orderNumber'] = (order_number or '').strip()
    billing = _apply_sdk_billing_defaults(billing, partner=partner, env=env)

    missing = [
        field_name for field_name in const.INIT_REQUIRED_FIELDS
        if not billing.get(field_name)
    ]
    if missing:
        raise UserError(_(
            'Missing required Tilopay fields: %s',
            ', '.join(missing),
        ))
    return billing


def build_sdk_payload(provider, partner, amount, currency, order_number, access_token, transaction=None):
    amount_value = float(amount)
    if amount_value <= 0:
        raise UserError(_('The payment amount must be greater than zero.'))

    base_url = provider.get_base_url()
    if not base_url and not (provider.tilopay_return_url or '').strip():
        raise UserError(_('Configure the system parameter web.base.url before taking payments.'))

    billing = prepare_billing_fields(
        partner, order_number, transaction=transaction, env=provider.env,
    )
    redirect_url = get_redirect_url(provider)
    if 'localhost' in redirect_url or '127.0.0.1' in redirect_url:
        _logger.warning(
            'Tilopay redirect URL is not public (%s). '
            'Set web.base.url or Tilopay Return URL on the payment provider.',
            redirect_url,
        )

    return {
        'token': access_token,
        'currency': currency.name if hasattr(currency, 'name') else currency,
        'language': 'es',
        'amount': amount_value,
        'capture': 1,
        'redirect': redirect_url,
        'subscription': 0,
        'hashVersion': 'V2',
        **billing,
    }


def redact_for_log(payload):
    if not isinstance(payload, dict):
        return payload
    return {
        key: ('***' if key in const.SENSITIVE_LOG_KEYS and value else value)
        for key, value in payload.items()
    }
