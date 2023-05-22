# -*- coding: utf-8 -*-
# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

from odoo import api, models, fields, _
from odoo.exceptions import UserError

from odoo.addons.authorize_net.models import misc


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.model
    def default_get(self, fields):
        res = super(AccountPaymentRegister, self).default_get(fields)
        context = dict(self.env.context or {})
        company = self.env.company
        if context.get('is_register_pay') and context.get('active_id') and context.get('active_model') == 'account.move':
            transaction_ids = []
            payment_types = self.env['payment.provider'].sudo().search([('code', '=', 'authorize'), \
                        ('company_id', '=', company.id)]).mapped('authorize_payment_method_type')
            invoice_id = self.env['account.move'].browse(context['active_id'])
            invoice_partner_id = invoice_id.partner_id
            company_invoice_id = self.env['account.move'].search([
                                    ('user_id', '=', self.env.uid),
                                    ('id', '=', invoice_id.id),
                                    ('company_id', 'child_of', [company.id])], limit=1)
            authorize_partner_ids = invoice_partner_id.authorize_partner_ids.filtered(lambda x: x.provider_type == 'credit_card')
            if not authorize_partner_ids and invoice_partner_id.parent_id:
                authorize_partner_ids = invoice_partner_id.parent_id.authorize_partner_ids.filtered(lambda x: x.provider_type == 'credit_card')

            cid, token = False, False
            if 'credit_card' in payment_types:
                if company_invoice_id:
                    cid = authorize_partner_ids.filtered(lambda x: x.company_id.id == invoice_id.company_id.id and \
                            x.provider_type == 'credit_card')
                else:
                    cid = authorize_partner_ids.filtered(lambda x: x.company_id.id == company.id and \
                            x.provider_type == 'credit_card')
            # elif 'bank_account' in payment_types:
            #     if company_invoice_id:
            #         cid = authorize_partner_ids.filtered(lambda x: x.company_id.id == invoice_id.company_id.id and \
            #                 x.provider_type == 'bank_account')
            #     else:
            #         cid = authorize_partner_ids.filtered(lambda x: x.company_id.id == company.id and \
            #                 x.provider_type == 'bank_account')

            res['auth_partner_id'] = cid.id if cid else False

            if not cid:
                payment_token_ids = invoice_partner_id.payment_token_ids
                if not payment_token_ids and invoice_partner_id.parent_id:
                    payment_token_ids = invoice_partner_id.parent_id.payment_token_ids
                if company_invoice_id:
                    token = payment_token_ids.filtered(lambda x: x.company_id.id == company_invoice_id.company_id.id and \
                                x.provider_ref and x.provider_id.code == 'authorize' and \
                                x.provider_id.authorize_payment_method_type == self.authorize_payment_type)
                else:
                    token = payment_token_ids.filtered(lambda x: x.company_id.id == company.id and \
                                x.provider_ref and x.provider_id.code == 'authorize' and \
                                x.provider_id.authorize_payment_method_type == self.authorize_payment_type)

            if cid and invoice_id:
                res.update({
                    'merchant_id': cid.merchant_id if cid else False,
                    'customer_profile_id': cid.customer_profile_id if cid else token.authorize_profile,
                    'shipping_address_id': cid.shipping_address_id if cid else False,
                    'provider_id': cid and cid.provider_id.id if cid else token.provider_id.id,
                })

            if res.get('customer_profile_id') and invoice_id and \
                    invoice_id.move_type in ['out_refund', 'in_refund']:
                is_refund_ref = False
                if invoice_id.transaction_ids.filtered(lambda tx: tx.state == 'done'):
                    is_refund_ref = True
                for transaction in invoice_id.transaction_ids.filtered(lambda x: x.transaction_type == 'debit' and not x.refund_amount >= x.amount and x.state == 'done' and x.payment_id and x.payment_id.authorize_payment_type == 'credit_card'):
                    remaining_amount = transaction.amount - transaction.refund_amount
                    if remaining_amount:
                        auth_invoice_refund_id = self.env['authorize.invoice.refund'].create({
                            'partner_id': transaction.partner_id.id,
                            'transaction_id': transaction.provider_reference,
                            'payment_token_id': transaction.token_id and transaction.token_id.id,
                            'credit_amount': transaction.amount,
                            'refund_amount': remaining_amount,
                            'available_amount': remaining_amount,
                            'payment_transaction_id': transaction.id,
                            'provider_id': transaction.provider_id.id,
                            'currency_id': transaction.currency_id.id,
                            'customer_profile_id': transaction.payment_id.customer_profile_id,
                            'merchant_id': transaction.payment_id.merchant_id
                        })
                        transaction_ids.append(auth_invoice_refund_id.id)
                        res.update({
                            'merchant_id': False,
                            'shipping_address_id': False,
                            'provider_id': False,
                        })
                res.update({
                    'auth_invoice_refund_ids': [(6, 0, transaction_ids)],
                    'partner_id': invoice_id.partner_id.id,
                    'is_refund_ref': is_refund_ref
                })
        return res

    def _get_billing_partner_domain(self):
        domain = [('type', '=', 'invoice')]
        context = dict(self.env.context) or {}
        if context.get('active_id') and context.get('active_model') == 'account.move':
            invoice_id = self.env['account.move'].browse(context['active_id'])
            domain.append(('parent_id', '=', invoice_id.partner_id.id))
        return domain

    provider_id = fields.Many2one('payment.provider', string='Provider', copy=False)
    authorize_payment_type = fields.Selection([('credit_card', 'Credit Card'), ('bank_account', 'eCheck.Net')],
                                              'Authorize Transaction', default="credit_card", copy=False)
    transaction_type = fields.Selection([('authorize', 'Authorize'), ('capture', 'Capture'), ('auth_capture', 'Authorize and Capture')],
                                        'Transaction Type', default='authorize', copy=False, states={'draft': [('readonly', False)]}, readonly=True)
    auth_partner_id = fields.Many2one('res.partner.authorize', string="Customer Profile", \
                            domain="[('provider_type', '=', authorize_payment_type)]")
    merchant_id = fields.Char(string='Merchant', readonly=True, copy=False)
    customer_profile_id = fields.Char(string='Customer Profile ID', size=64, readonly=True, copy=False)
    shipping_address_id = fields.Char(string='Shipping ID', size=64, readonly=True, copy=False)
    bank_id = fields.Many2one('res.partner.bank', string='Bank Account', domain="[('partner_id','=', partner_id), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
                              copy=False)
    transaction_id = fields.Char('Transaction ID', copy=False, readonly=True)
    payment_authorize = fields.Boolean('Payment via Authorize.Net', copy=False)
    is_refund_ref = fields.Boolean('Is Refund Reference', copy=False)
    auth_invoice_refund_ids = fields.Many2many('authorize.invoice.refund', string="Transaction", ondelete='cascade', copy=False)
    # without save card
    is_wo_save_card = fields.Boolean('Direct Payment(Without Save Card)', default=False, copy=False)
    cc_type = fields.Selection([('americanexpress', 'American Express'),
                                ('visa', 'Visa'),
                                ('mastercard', 'Mastercard'),
                                ('discover', 'Discover'),
                                ('dinersclub', 'Diners Club'),
                                ('jcb', 'JCB')], 'Card Type', readonly=True, copy=False)
    cc_number = fields.Char('Card Number', size=16, copy=False)
    cc_cvv = fields.Char('CVV', size=4, copy=False)
    cc_month = fields.Selection([('01', '01'), ('02', '02'), ('03', '03'), ('04', '04'),
                                 ('05', '05'), ('06', '06'), ('07', '07'), ('08', '08'),
                                 ('09', '09'), ('10', '10'), ('11', '11'), ('12', '12'),
                                 ('xx', 'xx')], 'Expires Month', copy=False)
    cc_year = fields.Char('Expires Year', size=64, copy=False)
    billing_partner_id = fields.Many2one('res.partner', 'Billing Partner', domain=_get_billing_partner_domain)

    @api.onchange('payment_authorize')
    def onchange_payment_authorize(self):
        context = dict(self.env.context or {})
        if not self.payment_authorize:
            self.payment_token_id = False

        # invoice_id, journal_id = False, False
        # payment_token_id, payment_method_line_id = False, False
        # if context.get('active_id') and context.get('active_model') == 'account.move':
        #     invoice_id = self.env['account.move'].browse(context['active_id'])
        # if self.payment_authorize and invoice_id and not self.is_wo_save_card:
        #     invoice_partner_id = invoice_id.partner_id
        #     if not invoice_partner_id.authorize_partner_ids.filtered(lambda x: \
        #         x.provider_type == 'credit_card') and invoice_partner_id.parent_id and \
        #         invoice_partner_id.parent_id.authorize_partner_ids.filtered(lambda x: x.provider_type == 'credit_card'):
        #         invoice_partner_id = invoice_partner_id.parent_id

        #     payment_token_ids = self.env['payment.token'].search([
        #                         ('partner_id','=', invoice_partner_id.id),
        #                         ('authorize_card', '=', True),
        #                         '|',
        #                         ('company_id', '=', False),
        #                         ('company_id', '=', invoice_id.company_id.id)])
        #     return {'payment_token_id': payment_token_ids.ids}
        #     # self.payment_token_id = payment_token_id.id if payment_token_id else False

    @api.onchange('is_wo_save_card', 'cc_number')
    def onchange_cc_number(self):
        # cc type will be set based on cc number
        if self.cc_number:
            self.cc_type = misc.cc_type(self.cc_number) or False
        # Value will be set / unset
        if self.is_wo_save_card:
            self.payment_token_id = False
        else:
            self.cc_number = self.cc_type = self.cc_year = self.cc_month = self.cc_cvv = False

    # @api.onchange("cc_number", "is_wo_save_card", "payment_authorize")
    # def onchange_cc_number(self):
    #     context = dict(self.env.context or {})
    #     invoice_id, journal_id, payment_token_id, payment_method_line_id = False, False, False, False
    #     if context.get('active_id') and context.get('active_model') == 'account.move':
    #         invoice_id = self.env['account.move'].browse(context['active_id'])

    #     if self.payment_authorize and invoice_id:
    #         payment_methods = self.journal_id and self.journal_id.inbound_payment_method_line_ids
    #         if not payment_methods and self.provider_id and self.provider_id.provider == 'authorize':
    #             raise UserError(_("Please configure Payment Methods in %s journal" %(self.journal_id.name)))
    #         auth_transaction = invoice_id.authorized_transaction_ids.filtered(lambda x: x.transaction_type == 'debit')
    #         self.amount = float(auth_transaction.amount) if auth_transaction and len(auth_transaction) == 1 else invoice_id.amount_residual
    #         from_currency_id = invoice_id.currency_id or invoice_id.company_id.currency_id
    #         to_currency_id = self.currency_id
    #         if from_currency_id and to_currency_id and from_currency_id != to_currency_id:
    #             self.amount = from_currency_id._convert(self.amount, to_currency_id, self.company_id or self.provider_id.journal_id.company_id, fields.Date.today())
    #         journal_id = self.env['account.journal'].search([('type', '=', 'bank'),
    #                                                          '|',('company_id', '=', False), ('company_id', '=', invoice_id.company_id.id)], limit=1)
    #         payment_token_id = self.env['payment.token'].search([('partner_id','=', invoice_id.partner_id.id),
    #                                                              ('authorize_card', '=', True),
    #                                                              '|', ('company_id', '=', False), ('company_id', '=', invoice_id.company_id.id)], limit=1)
    #         payment_method_line_id = self.env['account.payment.method.line'].search([('code','=','authorize')])
    #     elif not self.payment_authorize and invoice_id:
    #         self.is_wo_save_card = False
    #         journal_id = self.env['account.journal'].search([('type', '=', 'bank'),
    #                                                          '|',('company_id', '=', False), ('company_id', '=', invoice_id.company_id.id)], limit=1)
    #     self.journal_id = journal_id.id if journal_id else False
    #     if not self.is_wo_save_card:
    #         self.payment_token_id = payment_token_id.id if payment_token_id else False
    #     self.payment_method_line_id = payment_method_line_id.id if payment_method_line_id else False

    # @api.onchange('payment_token_id', 'payment_authorize')
    # def onchange_token_id(self):
    #     self.ensure_one()
    #     context = dict(self.env.context or {})
    #     if self.payment_type == 'inbound' and self.payment_token_id and self.payment_authorize and not self.payment_token_id.authorize_card:
    #         self.update({
    #             'merchant_id': False,
    #             'customer_profile_id': self.payment_token_id.authorize_profile,
    #             'shipping_address_id': False,
    #             'provider_id': self.payment_token_id.provider_id.id
    #         })
    #     elif self.payment_type == 'inbound' and context.get('is_register_pay') and context.get('active_id') and context.get('active_model') == 'account.move':
    #         invoice_id = self.env['account.move'].browse(context['active_id'])
    #         company_invoice_id = self.env['account.move'].search([('company_id', 'child_of', [self.env.company.id]),
    #                                                               ('user_id', '=', self.env.uid),
    #                                                               ('id', '=', invoice_id.id)], limit=1)
    #         cid = False
    #         if company_invoice_id:
    #             cid = invoice_id.partner_id.authorize_partner_ids.filtered(lambda x: x.company_id.id == invoice_id.company_id.id)
    #         else:
    #             cid = invoice_id.partner_id.authorize_partner_ids.filtered(lambda x: x.company_id.id == self.env.company.id)
    #         if cid:
    #             self.update({
    #                 'merchant_id': cid.merchant_id,
    #                 'customer_profile_id': cid.customer_profile_id,
    #                 'shipping_address_id': cid.shipping_address_id,
    #                 'provider_id': cid.provider_id.id
    #             })

    def _create_payments(self):
        payments = super(AccountPaymentRegister, self)._create_payments()
        self.write({
            'cc_number': '',
            'cc_cvv': '',
            'cc_type': '',
            'cc_year': '',
            'cc_month': ''
        })
        return payments

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super(AccountPaymentRegister, self)._create_payment_vals_from_wizard(batch_result=batch_result)
        if self.payment_authorize:
            payment_vals.update({
                'cc_type': self.cc_type,
                'cc_number': self.cc_number,
                'cc_cvv': self.cc_cvv,
                'cc_month': self.cc_month,
                'cc_year': self.cc_year,
                'provider_id': self.provider_id.id,
                'authorize_payment_type': self.authorize_payment_type,
                'transaction_type': self.transaction_type,
                'merchant_id': self.merchant_id,
                'customer_profile_id': self.customer_profile_id,
                'shipping_address_id': self.shipping_address_id,
                # 'bank_id': self.bank_id.id,
                'transaction_id': self.transaction_id,
                'payment_authorize': self.payment_authorize,
                'is_refund_ref': self.is_refund_ref,
                'auth_invoice_refund_ids': self.auth_invoice_refund_ids.ids,
                'is_wo_save_card': self.is_wo_save_card,
                'billing_partner_id': self.billing_partner_id.id,
                'auth_partner_id': self.auth_partner_id and self.auth_partner_id.id or False,
            })
            if not self.is_wo_save_card:
                payment_vals.update({'payment_token_id': self.payment_token_id.id})
        return payment_vals
