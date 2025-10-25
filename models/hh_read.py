from odoo import models, fields

class EnergyHHRead(models.Model):
    _name = 'energy.hh.read'
    _description = 'Half-Hourly Energy Read'

    meter_product_id = fields.Many2one('product.product', string='Meter', required=True)
    ts_utc = fields.Datetime(string='Timestamp (UTC)', required=True, index=True)
    kwh = fields.Float(required=True)
    kvarh = fields.Float()
    quality_flag = fields.Selection([
        ('A','Actual'),('E','Estimate'),('S','Substitute')
    ], default='A', index=True)
