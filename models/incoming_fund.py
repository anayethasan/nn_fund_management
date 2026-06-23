from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class IncomingFund(models.Model):
    _name = 'nn.incoming.fund'
    _description = 'Incoming Fund'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'transaction_ref'
 
 
    fund_account_id = fields.Many2one(
        comodel_name='nn.fund.account',
        string='Fund Account',
        required=True,
        ondelete='restrict',
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    transaction_ref = fields.Char(
        string='Transaction Reference',
        required=True,
        tracking=True,
        copy=False,
        help='Unique reference per fund account. Same ref cannot be used twice for the same account.',
    )
    sender = fields.Char(
        string='Sender or Source',
        required=True,
    )
    description = fields.Text(string='Description')
    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        string='Attachments',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='fund_account_id.company_id',
        store=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='fund_account_id.currency_id',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    confirmed_by = fields.Many2one(
        comodel_name='res.users',
        string='Confirmed By',
        readonly=True,
        copy=False,
    )
    confirmed_date = fields.Datetime(
        string='Confirmed On',
        readonly=True,
        copy=False,
    )
    
    # SQL Constraint
    _sql_constraints = [
        (
            'transaction_ref_account_unique',
            'UNIQUE(transaction_ref, fund_account_id)',
            'This transaction reference already exists for the selected fund account.',
        ),
        (
            'amount_positive',
            'CHECK(amount > 0)',
            'Incoming fund amount must be greater than zero.',
        ),
    ]
    
    #Python Constraint
    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('Incoming fund amount must be greater than zero.')
            
    #Actions
    def action_confirm(self):
        """
        Only Finance Users can confirm.
        On confirmation, the amount is added to the account's unassigned balance
        via the computed field on FundAccount.
        """
        self._check_finance_user()
        for rec in self:
            if rec.state != 'draft':
                raise UserError(f'Only draft incoming funds can be confirmed. "{rec.transaction_ref}" is {rec.state}.')
            rec.write({
                'state': 'confirmed',
                'confirmed_by': self.self.env.user.id,
                'confirmed_date': fields.Datetime.now(),
            })
            # rec.fund_account_id._compute_balances()
            
    
    def action_cancel(self):
        """
        Confirmed records cannot be cancelled without authorization.
        Only authorized users (group_finance_user or fund_admin) can cancel confirmed funds.
        """
        self._check_finance_user()
        for rec in self:
            if rec.state == 'cancelled':
                raise UserError('This record is already cancelled.')
            if rec.state == 'confirmed':
                available = rec.fund_account_id.unassigned_balance
                if available < rec.amount:
                    raise UserError(
                        f'Cannot cancel: only {available} is available unassigned, '
                        f'but this fund added {rec.amount}. Some amount may already be '
                        'allocated or on hold.'
                    )
            rec.state = 'cancelled'
            rec.fund_account_id._compute_balances()
    
    def action_reset_to_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError('Only cancelled records can be reset to draft.')
            rec.state = 'draft'
            
    # Helpers
    def _check_finance_user(self):
        """Server-side security check — hiding buttons alone is not enough."""
        if not (
            self.env.user.has_group('nn_fund_management.group_finance_user')
            or 
            self.env.user.has_group('nn_fund_management.group_fund_admin')
        ):
            raise UserError('Only Finance Users or Fund Administrators can perform this action.')
    
    # Prevent deletion of confirmed records
    def unlink(self):
        for rec in self:
            if rec.state == 'confirmed':
                raise UserError(
                    f'Confirmed incoming fund "{rec.transaction_ref}" cannot be deleted. '
                    'Cancel it first.'
                )
        return super().unlink()