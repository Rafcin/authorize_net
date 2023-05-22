# -*- coding: utf-8 -*-
# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    authorize_cc = fields.Boolean('Authorize Payment', default=False)

    # def _get_authorize_domain(self):
    #     context = dict(self.env.context or {})
    #     domain = []
    #     if context.get('invoice_id'):
    #         invoice_id = self.env['account.move'].browse(context['invoice_id'])
    #         if context.get('payment_authorize'):
    #             domain = [
    #                 ('type', '=', 'bank'),
    #                 ('authorize_cc', '=', True),
    #                 ('company_id', '=', invoice_id.company_id.id)
    #             ]
    #         else:
    #             domain = [
    #                 ('type', 'in', ['bank', 'cash']),
    #                 ('company_id', '=', invoice_id.company_id.id)
    #             ]
    #     return domain

    # @api.model
    # def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
    #     context = dict(self.env.context or {})
    #     if context.get('invoice_id'):
    #         args = (args or []) + self._get_authorize_domain()
    #     return super(AccountJournal, self)._name_search(name=name, args=args, operator=operator, limit=limit, name_get_uid=name_get_uid)

    # @api.constrains('authorize_cc')
    # def _check_authorize_cc(self):
    #     if self.authorize_cc and self.type != 'bank':
    #         raise ValidationError(_('For Authorize.Net payment type must be as a Bank!'))
