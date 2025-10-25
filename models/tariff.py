from odoo import models, fields

class EnergyTariffRate(models.Model):
    _name = 'energy.tariff.rate'
    _description = 'Supplier Tariff Rate'

    name = fields.Char()
    supplier_id = fields.Many2one('res.partner', domain=[('supplier_rank','>',0)], required=True)
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)
    unit_rate_p_per_kwh = fields.Float()
    standing_gbp_per_day = fields.Float()
    capacity_rate_gbp_per_kva_month = fields.Float()
    reactive_rate_p_per_kvarh = fields.Float()