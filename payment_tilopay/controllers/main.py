# Copyright 2026 STARK LABS
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import logging

import werkzeug

from odoo import _, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request
from odoo.tools import mute_logger

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_tilopay import const, utils as tilopay_utils

_logger = logging.getLogger(__name__)


class TilopayController(http.Controller):

    def _check_form_access(self, access_token, partner_id, amount, currency_id, sale_order_id=None):
        """Validate portal order token or payment-link token without ACL noise."""
        if sale_order_id:
            try:
                tilopay_utils.get_sale_order_sudo(
                    request.env,
                    sale_order_id,
                    access_token=access_token,
                    partner_id=partner_id,
                    amount=amount,
                    currency_id=currency_id,
                )
                return
            except MissingError:
                raise werkzeug.exceptions.NotFound()
            except AccessError:
                raise werkzeug.exceptions.NotFound()
        if not payment_utils.check_access_token(access_token, partner_id, amount, currency_id):
            raise werkzeug.exceptions.NotFound()

    @http.route(
        const.FORM_VALUES_URL,
        type='json',
        auth='public',
    )
    def tilopay_form_values(
        self,
        provider_id,
        partner_id,
        amount,
        currency_id,
        access_token,
        sale_order_id=None,
        transaction_reference=None,
        is_validation=False,
    ):
        """Return Tilopay.Init() payload for the portal payment form."""
        provider_sudo = request.env['payment.provider'].sudo().browse(provider_id).exists()
        if not provider_sudo or provider_sudo.code != 'tilopay':
            raise ValidationError(_('Invalid payment provider.'))

        partner_sudo = request.env['res.partner'].sudo().browse(partner_id).exists()
        if not partner_sudo:
            raise ValidationError(_('Customer not found.'))

        currency_sudo = request.env['res.currency'].sudo().browse(currency_id).exists()
        if not currency_sudo:
            raise ValidationError(_('Currency not found.'))

        amount_value = float(amount or 0)
        sale_order_id = tilopay_utils.parse_int(sale_order_id) or tilopay_utils.resolve_sale_order_id(
            request.env,
        )
        self._check_form_access(
            access_token, partner_id, amount_value, currency_id, sale_order_id=sale_order_id,
        )
        if is_validation:
            amount_value = provider_sudo._get_validation_amount()

        transaction = None
        order_number = None
        if transaction_reference:
            transaction = tilopay_utils.get_transaction_sudo(
                request.env,
                transaction_reference,
                access_token=access_token,
                partner_id=partner_id,
                amount=amount_value,
                currency_id=currency_id,
                sale_order_id=sale_order_id,
            )
            order_number = transaction.reference
            amount_value = transaction.amount
            partner_sudo = transaction.partner_id
            currency_sudo = transaction.currency_id

        if not order_number:
            sale_order = request.env['sale.order'].sudo().browse(sale_order_id) if sale_order_id else request.env['sale.order']
            order_number = sale_order.name if sale_order.exists() else f'ODOO-{partner_id}'

        payload = tilopay_utils.build_sdk_payload(
            provider_sudo,
            partner_sudo,
            amount_value,
            currency_sudo,
            order_number,
            provider_sudo._tilopay_login(),
            transaction=transaction,
        )
        _logger.info(
            'Tilopay form values for partner %s (order %s): %s',
            partner_id,
            order_number,
            tilopay_utils.redact_for_log(payload),
        )
        return payload

    @http.route(
        const.LOG_ERROR_URL,
        type='json',
        auth='public',
    )
    def tilopay_log_error(self, reference, message, details=None):
        """Log Tilopay client-side payment errors for troubleshooting."""
        _logger.warning(
            'Tilopay client error on %s: %s%s',
            reference or '?',
            message,
            f' ({details})' if details else '',
        )
        return True

    @http.route(
        const.RETURN_URL,
        type='http',
        auth='public',
        methods=['GET', 'POST'],
        csrf=False,
    )
    def tilopay_return(self, **data):
        tx = request.env['payment.transaction'].sudo()
        try:
            tx = tx._get_tx_from_notification_data('tilopay', data)
            tx._handle_notification_data('tilopay', data)
        except Exception:
            _logger.exception('Unable to process Tilopay return notification')

        with mute_logger('werkzeug'):
            return request.redirect('/payment/status')
