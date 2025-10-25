from odoo import models, fields

class EnergyCommissionRule(models.Model):
    _name = 'energy.commission.rule'
    _description = 'Energy Commission Rule'

    name = fields.Char(required=True)
    supplier_id = fields.Many2one('res.partner', domain=[('supplier_rank', '>', 0)], required=True)
    year_duration = fields.Integer(string='Duration (years)', required=True)
    supplier_percent = fields.Float(string='Supplier % (of uplift)')
    broker_split_percent = fields.Float(string='Broker Split %')
    upfront_percent = fields.Float(string='Upfront %')
