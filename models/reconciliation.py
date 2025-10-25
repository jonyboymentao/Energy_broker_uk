from odoo import models, fields

class SupplierReconciliationLine(models.Model):
    _name = supplier.reconciliation.line
    _description = Supplier Commission Reconciliation Line

    contract_id = fields.Many2one(customer.contract, required=True, ondelete=cascade)
    date = fields.Date(default=fields.Date.context_today)
    com_amount = fields.Float(string=Supplier Commission Amount)
    note = fields.Char()

class BrokerReconciliationLine(models.Model):
    _name = broker.reconciliation.line
    _description = Broker Commission Reconciliation Line

    contract_id = fields.Many2one(customer.contract, required=True, ondelete=cascade)
    date = fields.Date(default=fields.Date.context_today)
    comm_amount = fields.Float(string=Broker Commission Amount)
    note = fields.Char()
