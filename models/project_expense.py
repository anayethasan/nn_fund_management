from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ProjectExpenseHead(models.Model):
    """
    Unified model for both Projects and Expense Heads.
    The 'budget_type' field distinguishes them.
    Balances are fully computed — cannot be manually edited.
    """
    _name = 'nn.project.expense'
    _description = 'Project or Expense Head'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'budget_type, name'
    
    name = fields.Char(string='Name', required=True, tracking=True)
    budget_type = fields.Selection(
        selection=[
            ('project', 'Project'),
            ('expense', 'Expense Head'),
        ],
        string='Type',
        required=True,
        default='project',
        tracking=True,
    )
    code = fields.Char(string='Code or Reference')
    description = fields.Text(string='Description')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    active = fields.Boolean(default=True)
    
    #Related Records (used to compute balances)
    allocation_ids = fields.One2many(
        comodel_name='nn.fund.allocation',
        inverse_name='project_expense_id',
        string='Allocations',
    )
    requisition_ids = fields.One2many(
        comodel_name='nn.fund.requisition',
        inverse_name='project_expense_id',
        string='Requisitions',
    )
    transfer_out_ids = fields.One2many(
        comodel_name='nn.fund.transfer',
        inverse_name='source_id',
        string='Outgoing Transfers',
    )
    transfer_in_ids = fields.One2many(
        comodel_name='nn.fund.transfer',
        inverse_name='destination_id',
        string='Incoming Transfers',
    )
    
    # Computed Balance Fields (All read-only) every can view but can't access
    total_allocated = fields.Monetary(
        string='Total Allocated',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
        help='Sum of all approved allocations to this project or expense head.',
    )
    incoming_transfers = fields.Monetary(
        string='Incoming Transfers',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
    )
    outgoing_transfers = fields.Monetary(
        string='Outgoing Transfers',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
    )
    requisition_hold = fields.Monetary(
        string='Requisition Hold',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
        help='Amount locked by submitted or gm_approved requisitions.',
    )
    transfer_hold = fields.Monetary(
        string='Transfer Hold',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
        help='Amount locked by submitted or gm_approved outgoing transfers.',
    )
    total_spent = fields.Monetary(
        string='Total Spent',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
        help='Sum of all posted bills against approved requisitions.',
    )
    available_balance = fields.Monetary(
        string='Available Balance',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
        help='Funds available for new requisitions or transfers. Cannot go negative.',
    ) 
    
    #Compute
    @api.depends(
        'allocation_ids.amount', 'allocation_ids.state',
        'requisition_ids.requested_amount', 'requisition_ids.state',
        'requisition_ids.bill_ids.amount', 'requisition_ids.bill_ids.state',
        'transfer_out_ids.amount', 'transfer_out_ids.state',
        'transfer_in_ids.amount', 'transfer_in_ids.state',
    )
    def _compute_balances(self):
        """
        Balance formula:
          available = total_allocated
                    + incoming_transfers
                    - outgoing_transfers (approved)
                    - requisition_hold
                    - transfer_hold
                    - total_spent
 
        Hold states: 'submitted', 'gm_approved'  (pending final approval)
        Final states: 'approved'
        """
        pending_states = ['submitted', 'gm_approved']
 
        for rec in self:
            # 1. Total from approved allocations
            total_allocated = sum(
                rec.allocation_ids.filtered(lambda a: a.state == 'approved').mapped('amount')
            )
 
            # 2. Incoming approved transfers
            incoming = sum(
                rec.transfer_in_ids.filtered(lambda t: t.state == 'approved').mapped('amount')
            )
 
            # 3. Outgoing approved transfers
            outgoing = sum(
                rec.transfer_out_ids.filtered(lambda t: t.state == 'approved').mapped('amount')
            )
 
            # 4. Requisition hold (pending approval)
            req_hold = sum(
                rec.requisition_ids.filtered(lambda r: r.state in pending_states).mapped('requested_amount')
            )
 
            # 5. Transfer hold (pending outgoing transfers)
            trans_hold = sum(
                rec.transfer_out_ids.filtered(lambda t: t.state in pending_states).mapped('amount')
            )
 
            # 6. Total spent = sum of all posted bills for this project/expense
            spent = sum(
                bill.amount
                for req in rec.requisition_ids.filtered(lambda r: r.state in ['approved', 'closed'])
                for bill in req.bill_ids.filtered(lambda b: b.state == 'posted')
            )
 
            available = total_allocated + incoming - outgoing - req_hold - trans_hold - spent
 
            rec.total_allocated = total_allocated
            rec.incoming_transfers = incoming
            rec.outgoing_transfers = outgoing
            rec.requisition_hold = req_hold
            rec.transfer_hold = trans_hold
            rec.total_spent = spent
            rec.available_balance = available
            
    # Prevent manual write on balance fields
    # def write(self, vals):
    #     balance_fields = {
    #         'total_allocated', 'available_balance', 'requisition_hold',
    #         'transfer_hold', 'total_spent', 'incoming_transfers', 'outgoing_transfers',
    #     }
    #     if balance_fields & set(vals.keys()):
    #         raise ValidationError('Balance fields are calculated automatically and cannot be edited manually.')
    #     return super().write(vals)
    
    # Constraint
    _sql_constraints = [
        (
            'name_type_company_unique',
            'UNIQUE(name, budget_type, company_id)',
            'A project or expense head with this name already exists for this company.',
        ),
    ]
    
    @api.constrains('available_balance')
    def _check_no_negative_balance(self):
        for rec in self:
            if rec.available_balance < 0:
                raise ValidationError(
                    f'"{rec.name}" would have a negative available balance. '
                    'This operation is not allowed.'
                )