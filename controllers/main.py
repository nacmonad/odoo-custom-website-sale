import logging
from odoo import http, tools, _
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.osv import expression, Command

_logger = logging.getLogger(__name__)

class CustomWebsiteSale(WebsiteSale):

    def _validate_transaction_for_order(self, transaction, sale_order_id):
        """
        Perform final checks against the transaction & sale_order.
        Override me to apply payment unrelated checks & processing
        """
        return

    @http.route(
        '/shop/payment/transaction/<int:order_id>', type='json', auth='public', website=True
    )
    def shop_payment_transaction(self, order_id, access_token, **kwargs):
        """ Create a draft transaction and return its processing values.

        :param int order_id: The sales order to pay, as a `sale.order` id
        :param str access_token: The access token used to authenticate the request
        :param dict kwargs: Locally unused data passed to `_create_transaction`
        :return: The mandatory values for the processing of the transaction
        :rtype: dict
        :raise: ValidationError if the invoice id or the access token is invalid
        """
        _logger.info("Starting shop_payment_transaction for order_id: %s", order_id)
        _logger.debug("Received kwargs: %s", kwargs)

        # Check the order id and the access token
        try:
            order_sudo = self._document_check_access('sale.order', order_id, access_token)
            _logger.debug("Order accessed successfully: %s", order_sudo)
        except MissingError as error:
            _logger.error("MissingError: %s", error)
            raise error
        except AccessError:
            _logger.error("AccessError: The access token is invalid.")
            raise ValidationError(_("The access token is invalid."))

        if order_sudo.state == "cancel":
            _logger.warning("ValidationError: The order has been canceled.")
            raise ValidationError(_("The order has been canceled."))

        order_sudo._check_cart_is_ready_to_be_paid()

        self._validate_transaction_kwargs(kwargs)
        kwargs.update({
            'partner_id': order_sudo.partner_invoice_id.id,
            'currency_id': order_sudo.currency_id.id,
            'sale_order_id': order_id,  # Include the SO to allow Subscriptions to tokenize the tx
        })
        if not kwargs.get('amount'):
            kwargs['amount'] = order_sudo.amount_total

        _logger.debug("Comparing amounts: kwargs['amount']=%s, order_sudo.amount_total=%s", kwargs['amount'], order_sudo.amount_total)
        if tools.float_compare(kwargs['amount'], order_sudo.amount_total, precision_rounding=order_sudo.currency_id.rounding):
            _logger.warning("ValidationError: The cart has been updated. Please refresh the page.")
            raise ValidationError(_("The cart has been updated. Please refresh the page."))

        tx_sudo = self._create_transaction(
            custom_create_values={'sale_order_ids': [Command.set([order_id])]}, **kwargs,
        )

        _logger.info("Transaction created successfully: %s", tx_sudo)

        # Store the new transaction into the transaction list and if there's an old one, we remove
        # it until the day the ecommerce supports multiple orders at the same time.
        request.session['__website_sale_last_tx_id'] = tx_sudo.id

        self._validate_transaction_for_order(tx_sudo, order_id)

        return tx_sudo._get_processing_values()
