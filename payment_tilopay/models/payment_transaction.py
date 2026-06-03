# Copyright 2026 STARK LABS
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

import json
import logging

from odoo import _, models
from odoo.exceptions import ValidationError

from odoo.addons.payment_tilopay import const, utils as tilopay_utils

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _get_specific_processing_values(self, processing_values):
        values = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'tilopay':
            return values
        return {
            'form_values': self.sudo().provider_id._tilopay_get_form_values(self.sudo()),
            'return_url': tilopay_utils.get_redirect_url(self.provider_id),
        }

    def _get_specific_secret_keys(self):
        if self.provider_code == 'tilopay':
            return {'form_values': None}.keys()
        return super()._get_specific_secret_keys()

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'tilopay' or len(tx) == 1:
            return tx

        return_data = self._tilopay_parse_return_data(notification_data)
        reference = return_data.get('reference')
        if not reference:
            raise ValidationError(_('Tilopay did not return a transaction reference.'))

        tx = self.search([
            ('reference', '=', reference),
            ('provider_code', '=', 'tilopay'),
        ], limit=1)
        if not tx:
            raise ValidationError(_('No Tilopay transaction found for reference %s.', reference))
        return tx

    def _process_notification_data(self, notification_data):
        super()._process_notification_data(notification_data)
        if self.provider_code != 'tilopay':
            return

        if not notification_data:
            self._set_canceled(_('The customer left the payment page.'))
            return

        return_data = self._tilopay_parse_return_data(notification_data)
        self._tilopay_warn_on_mismatch(return_data)

        provider_reference = (
            notification_data.get('tilopay-transaction')
            or notification_data.get('transactionId')
        )
        if provider_reference:
            self.provider_reference = provider_reference

        status = str(notification_data.get('code') or notification_data.get('status') or '')
        message = notification_data.get('message') or notification_data.get('description') or ''

        if status in const.STATUS_DONE:
            self._set_done()
        elif status in const.STATUS_CANCEL or (status.isdigit() and status != '1'):
            self._set_canceled(state_message=message or _('Payment was rejected.'))
        else:
            self._set_error(_('Tilopay returned an unexpected status: %s', status))

    def _tilopay_parse_return_data(self, notification_data):
        raw = notification_data.get('returnData')
        if not raw:
            return {}
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError) as error:
            raise ValidationError(_('Tilopay returned invalid return data.')) from error

    def _tilopay_warn_on_mismatch(self, return_data):
        amount = return_data.get('amount')
        currency_code = return_data.get('currency')
        if not amount or not currency_code:
            return

        currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
        if not currency:
            return

        if self.currency_id.compare_amounts(float(amount), self.amount) != 0:
            _logger.warning(
                'Tilopay amount mismatch on %s: expected %s, received %s',
                self.reference,
                self.amount,
                amount,
            )
        if currency != self.currency_id:
            _logger.warning(
                'Tilopay currency mismatch on %s: expected %s, received %s',
                self.reference,
                self.currency_id.name,
                currency.name,
            )
