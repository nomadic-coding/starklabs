# Copyright 2026 STARK LABS
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import REPORT_REASONS_MAPPING
from odoo.addons.payment_tilopay import const, utils as tilopay_utils

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('tilopay', 'Tilopay')],
        ondelete={'tilopay': 'set default'},
    )
    tilopay_api_key = fields.Char(
        string='API Key',
        required_if_provider='tilopay',
    )
    tilopay_api_user = fields.Char(
        string='API User',
        required_if_provider='tilopay',
        groups='base.group_system',
    )
    tilopay_api_password = fields.Char(
        string='API Password',
        required_if_provider='tilopay',
        groups='base.group_system',
    )
    tilopay_return_url = fields.Char(
        string='Return URL',
        help='Public HTTPS URL where Tilopay redirects after payment. '
             'Required when web.base.url is localhost. Example: '
             'https://your-domain.com/payment/tilopay/return',
    )

    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        self.filtered(lambda provider: provider.code == 'tilopay').update({
            'support_manual_capture': 'full_only',
            'support_refund': 'none',
            'support_tokenization': False,
            'support_express_checkout': False,
        })

    @api.model
    def _get_compatible_providers(
        self,
        company_id,
        partner_id,
        amount,
        currency_id=None,
        force_tokenization=False,
        is_express_checkout=False,
        is_validation=False,
        report=None,
        **kwargs,
    ):
        providers = super()._get_compatible_providers(
            company_id,
            partner_id,
            amount,
            currency_id=currency_id,
            force_tokenization=force_tokenization,
            is_express_checkout=is_express_checkout,
            is_validation=is_validation,
            report=report,
            **kwargs,
        )
        if not is_express_checkout:
            return providers

        blocked = providers.filtered(lambda provider: provider.code == 'tilopay')
        if blocked:
            payment_utils.add_to_report(
                report,
                blocked,
                available=False,
                reason=REPORT_REASONS_MAPPING['provider_not_available'],
            )
            providers -= blocked
        return providers

    @api.model
    def _setup_provider(self, provider_code):
        res = super()._setup_provider(provider_code)
        if provider_code == 'tilopay':
            self._tilopay_configure_inline_form()
        return res

    @api.model
    def _tilopay_configure_inline_form(self):
        inline_form = self.env.ref('payment_tilopay.inline_form', raise_if_not_found=False)
        if not inline_form:
            return
        self.search([('code', '=', 'tilopay')]).write({
            'inline_form_view_id': inline_form.id,
        })

    def _get_default_payment_method_codes(self):
        if self.code != 'tilopay':
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _tilopay_login(self):
        self.ensure_one()
        credentials = {
            'apiuser': (self.tilopay_api_user or '').strip(),
            'password': (self.tilopay_api_password or '').strip(),
            'key': (self.tilopay_api_key or '').strip(),
        }
        if not all(credentials.values()):
            raise UserError(_('Configure the Tilopay API credentials on the payment provider.'))

        try:
            response = requests.post(const.LOGIN_URL, json=credentials, timeout=15)
            response.raise_for_status()
            body = response.json()
        except requests.exceptions.Timeout as error:
            raise UserError(_('The Tilopay API timed out.')) from error
        except requests.exceptions.RequestException as error:
            raise UserError(_('Could not reach the Tilopay API.')) from error
        except ValueError as error:
            raise UserError(_('The Tilopay API returned an invalid response.')) from error

        token = body.get('access_token')
        if not token:
            message = body.get('message') or body.get('error') or _('Unknown error')
            raise UserError(_('Tilopay authentication failed: %s', message))
        return token

    def _tilopay_get_inline_form_values(
        self,
        amount,
        currency,
        partner_id,
        is_validation=False,
        payment_method_sudo=None,
        **kwargs,
    ):
        self.ensure_one()
        if is_validation:
            amount = self._get_validation_amount()

        partner = self.env['res.partner'].with_context(show_address=1).browse(partner_id).exists()
        if not partner:
            raise UserError(_('Customer not found.'))

        sale_order_id = tilopay_utils.resolve_sale_order_id(self.env, kwargs.get('sale_order_id'))
        sale_order = self.env['sale.order'].sudo().browse(sale_order_id) if sale_order_id else self.env['sale.order']
        order_number = sale_order.name if sale_order.exists() else f'ODOO-{partner_id}'

        payload = tilopay_utils.build_sdk_payload(
            self,
            partner,
            amount,
            currency,
            order_number,
            self._tilopay_login(),
        )
        _logger.info(
            'Tilopay inline form for partner %s: %s',
            partner_id,
            tilopay_utils.redact_for_log(payload),
        )
        return json.dumps(payload, ensure_ascii=False)

    def _tilopay_get_form_values(self, transaction):
        self.ensure_one()
        transaction.ensure_one()
        payload = tilopay_utils.build_sdk_payload(
            self,
            transaction.partner_id,
            transaction.amount,
            transaction.currency_id,
            tilopay_utils.document_reference(transaction),
            self._tilopay_login(),
            transaction=transaction,
        )
        _logger.info(
            'Tilopay backend form for %s: %s',
            transaction.reference,
            tilopay_utils.redact_for_log(payload),
        )
        return payload
