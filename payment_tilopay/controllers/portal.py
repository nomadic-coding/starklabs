# Copyright 2026 STARK LABS
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from odoo import Command, _, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request

from odoo.addons.payment.controllers.portal import PaymentPortal as PaymentPortalBase
from odoo.addons.payment_tilopay import utils as tilopay_utils
from odoo.addons.sale.controllers.portal import PaymentPortal as SalePaymentPortal


class PaymentPortal(SalePaymentPortal):

    @http.route()
    def portal_order_transaction(self, order_id, access_token, **kwargs):
        """Create a draft transaction without triggering sale.order ACL checks."""
        try:
            order_sudo = tilopay_utils.get_sale_order_sudo(
                request.env, order_id, access_token=access_token,
            )
        except MissingError as error:
            raise error
        except AccessError:
            raise ValidationError(_("The access token is invalid."))

        logged_in = not request.env.user._is_public()
        partner_sudo = request.env.user.partner_id if logged_in else order_sudo.partner_invoice_id
        self._validate_transaction_kwargs(kwargs)
        kwargs.update({
            'partner_id': partner_sudo.id,
            'currency_id': order_sudo.currency_id.id,
            'sale_order_id': order_id,
        })
        tx_sudo = self._create_transaction(
            custom_create_values={'sale_order_ids': [Command.set([order_id])]},
            **kwargs,
        )
        return tx_sudo._get_processing_values()

    def _get_extra_payment_form_values(self, sale_order_id=None, access_token=None, **kwargs):
        """Resolve sale orders with sudo to avoid portal ACL log noise on /payment/pay."""
        form_values = PaymentPortalBase._get_extra_payment_form_values(
            self,
            sale_order_id=sale_order_id,
            access_token=access_token,
            **kwargs,
        )
        if not sale_order_id:
            return form_values

        sale_order_id = self._cast_as_int(sale_order_id)
        order_sudo = tilopay_utils.get_sale_order_sudo(
            request.env,
            sale_order_id,
            access_token=access_token,
            partner_id=kwargs.get('partner_id'),
            amount=kwargs.get('amount'),
            currency_id=kwargs.get('currency_id'),
        )

        if order_sudo.state == 'cancel':
            form_values['amount'] = 0.0

        form_values.update({
            'transaction_route': order_sudo.get_portal_url(suffix='/transaction'),
            'landing_route': order_sudo.get_portal_url(),
            'access_token': order_sudo.access_token,
        })
        return form_values
