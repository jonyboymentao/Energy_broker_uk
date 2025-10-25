# -*- coding: utf-8 -*-
from odoo import models, fields


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    loa_count = fields.Integer(compute='_compute_broker_counts', string='LOAs')
    request_count = fields.Integer(compute='_compute_broker_counts', string='Price Requests')
    response_count = fields.Integer(compute='_compute_broker_counts', string='Supplier Responses')
    contract_count = fields.Integer(compute='_compute_broker_counts', string='Contracts')

    def _compute_broker_counts(self):
        for lead in self:
            lead.loa_count = self.env['customer.loa'].search_count([('lead_id', '=', lead.id)])
            lead.request_count = self.env['supplier.price.request'].search_count([('lead_id', '=', lead.id)])
            lead.response_count = self.env['supplier.price.response'].search_count([('lead_id', '=', lead.id)])
            lead.contract_count = self.env['customer.contract'].search_count([('lead_id', '=', lead.id)])

    def action_open_lead_loas(self):
        self.ensure_one()
        action = self.env.ref('energy_broker_uk.action_customer_loa').read()[0]
        action['domain'] = [('lead_id', '=', self.id)]
        action['context'] = {'default_lead_id': self.id, 'default_partner_id': self.partner_id.id}
        return action

    def action_open_lead_requests(self):
        self.ensure_one()
        action = self.env.ref('energy_broker_uk.action_supplier_price_request').read()[0]
        action['domain'] = [('lead_id', '=', self.id)]
        action['context'] = {'default_lead_id': self.id}
        return action

    def action_open_lead_responses(self):
        self.ensure_one()
        action = self.env.ref('energy_broker_uk.action_supplier_price_response').read()[0]
        action['domain'] = [('lead_id', '=', self.id)]
        action['context'] = {'default_lead_id': self.id}
        return action

    def action_open_lead_contracts(self):
        self.ensure_one()
        action = self.env.ref('energy_broker_uk.action_customer_contract').read()[0]
        action['domain'] = [('lead_id', '=', self.id)]
        action['context'] = {'default_lead_id': self.id, 'default_partner_id': self.partner_id.id}
        return action
