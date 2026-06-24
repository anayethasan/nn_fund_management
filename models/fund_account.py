# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError

class FundAccount(models.Model):
    _name = "nn.fund.account"
    _description = "Fund Account"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    
    # Basic info
    name = fields.Char(
        string='Account name',
        required=True,
        tracking=True
    )
    account_type = fields.Selection(
        selection=[
            ('bank', 'Bank'),
            ('cash', 'Cash'),
            ('other', 'Other'),
        ],
        string='Account Type',
        required=True,
        default='bank',
        tracking=True
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    
    #Related Record
    incoming_fund_ids = fields.One2many(
        comodel_name='nn.incoming.fund',
        inverse_name='fund_account_id',
        string='Incoming Funds',
    )
    allocation_ids = fields.One2many(
        comodel_name='nn.fund.allocation',
        inverse_name='fund_account_id',
        string='Allocations',
    )
    
    #Computed Balance Fields (read-only, cannot be manually edited)
    total_received = fields.Monetary(
        string='Total Received',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
        help='Sum of all confirmed incoming funds.',
    )
    unassigned_balance = fields.Monetary(
        string='Unassigned Balance',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
        help='Available funds not yet allocated or on hold.',
    )
    held_amount = fields.Monetary(
        string='On Hold',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
        help='Funds locked by pending allocation requests (submitted → approved).',
    )
    assigned_amount = fields.Monetary(
        string='Total Assigned',
        compute='_compute_balances',
        store=True,
        currency_field='currency_id',
        help='Funds successfully moved to projects or expense heads.',
    )
    
    #Computed
    @api.depends(
        'incoming_fund_ids.amount',
        'incoming_fund_ids.state',
        'allocation_ids.amount',
        'allocation_ids.state',
    )
    def _compute_balances(self):
        """
        Core balance logic this is the logic where we doo double-spending is prevented.
        
        Money flow:
          confirmed income  → unassigned_balance
          allocation submit → unassigned -= amount, held += amount
          allocation approve → held -= amount, assigned += amount
          allocation reject/cancel → held -= amount, unassigned += amount
        """
        for account in self:
            confirmed_funds = account.incoming_fund_ids.filtered(
                lambda f: f.state == 'confirmed'
            )
            total_received = sum(confirmed_funds.mapped('amount'))
            held_states = ['submitted', 'gm_approved']
            held_allocations = account.allocation_ids.filtered(
                lambda a: a.state in held_states
            )
            held = sum(held_allocations.mapped('amount'))
            
            # approved state
            approved_allocations = account.allocation_ids.filtered(
                lambda a: a.state == 'approved'
            )
            assigned = sum(approved_allocations.mapped('amount'))
            
            # unassigned = total received - held - assigned
            unassigned = total_received - held - assigned
            account.total_received = total_received
            account.held_amount = held
            account.assigned_amount = assigned
            account.unassigned_balance = unassigned
            
            #prevent manual write on balance fields
    def write(self, vals):
        protected = {'total_received', 'unassigned_balance', 'held_amount', 'assigned_amount'}
        if protected & set(vals.keys()):
            raise ValidationError('Balance fields are calculated automatically and cannot be edited manually.')
        return super().write(vals)
            
    # constraints 
    _sql_constraints = [
        (
            'name_company_unique',
            'UNIQUE(name, company_id)',
            'A fund account with this name already exists for this company.',
        ),
    ]
    @api.constrains('unassigned_balance')
    def _check_no_negative_balance(self):
        for account in self:
            if account.unassigned_balance < 0:
                raise ValidationError(
                    f'Fund account {account.name} would have a negative unassigned balance.'
                )
                
    
    # smart button
    def action_view_incoming_funds(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Incoming Funds',
            'res_model': 'nn.incoming.fund',
            'view_mode': 'list,form',
            'domain': [('fund_account_id', '=', self.id)],
            'context': {'default_fund_account_id': self.id},
        }
 
    def action_view_allocations(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Allocations',
            'res_model': 'nn.fund.allocation',
            'view_mode': 'list,form',
            'domain': [('fund_account_id', '=', self.id)],
            'context': {'default_fund_account_id': self.id},
        }
