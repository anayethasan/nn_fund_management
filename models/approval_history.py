from odoo import models, fields, api 
from odoo.exceptions import UserError

class ApprovalHistory(models.Model):
    """
    Shared audit log for all approval-based documents.
    Used by: FundAllocation, FundRequisition, FundTransfer.
 
    Uses a generic reference (res_model + res_id) so the same model
    can serve all three document types without duplication.
    """
    _name = 'nn.approval.history'
    _description = 'Approval History'
    _order = 'date desc, id desc'
    
    res_model = fields.Char(
        string='Document Model',
        required=True,
        readonly=True,
        index=True,
        help='Technical name of the related document model (e.g. nn.fund.allocation).',
    )
    res_id = fields.Integer(
        string='Document ID',
        required=True,
        readonly=True,
        index=True,
    )
    res_name = fields.Char(
        string='Document Reference',
        readonly=True,
        help='Human-readable reference number of the document.',
    )
    
    #Who what when
    approver_id = fields.Many2one(
        comodel_name='res.users',
        string='Action By',
        required=True,
        readonly=True,
        ondelete='restrict',
    )
    approval_level = fields.Selection(
        selection=[
            ('submit', 'Submission'),
            ('gm', 'GM Approval'),
            ('md', 'MD Approval'),
            ('cancel', 'Cancellation'),
            ('reject', 'Rejection'),
        ],
        string='Action Level',
        required=True,
        readonly=True,
    )
    decision = fields.Selection(
        selection=[
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Decision',
        required=True,
        readonly=True,
    )
    date = fields.Datetime(
        string='Date & Time',
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    comment = fields.Text(string='Comment or Remark', readonly=True)
    
    # Financial Context
    amount = fields.Monetary(
        string='Amount',
        readonly=True,
        currency_field='currency_id',
        help='Amount on the document at the time of this action.',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        readonly=True,
    )
    fund_account_id = fields.Many2one(
        comodel_name='nn.fund.account',
        string='Fund Account',
        readonly=True,
    )
    project_expense_id = fields.Many2one(
        comodel_name='nn.project.expense',
        string='Project or Expense Head',
        readonly=True,
    )
    
    #Previous and new state for full audit trail
    state_before = fields.Char(string='Status Before', readonly=True)
    state_after = fields.Char(string='Status After', readonly=True)
    
    #Prevent any modification after creating 
    def write(self, vals):
        raise UserError('Approval history records are immutable and cannot be edited.')
 
    def unlink(self):
        raise UserError('Approval history records cannot be deleted.')
    
    # Helper : Called by Allocation, Requisition, Transfer 
    @api.model
    def log_action(self, document, approval_level, decision, comment='', state_before=None, state_after=None):
        """
        Convenience method to create an audit entry.
        """
        fund_account = getattr(document, 'fund_account_id', False) or False
        project_expense = getattr(document, 'project_expense_id', False) or False
        amount = getattr(document, 'amount', False) or getattr(document, 'requested_amount', 0.0)
        currency = (
            getattr(document, 'currency_id', False)
            or (fund_account and fund_account.currency_id)
            or self.env.company.currency_id
        )
 
        self.create({
            'res_model': document._name,
            'res_id': document.id,
            'res_name': document.display_name,
            'approver_id': self.env.uid,
            'approval_level': approval_level,
            'decision': decision,
            'date': fields.Datetime.now(),
            'comment': comment or '',
            'amount': amount,
            'currency_id': currency.id if currency else False,
            'fund_account_id': fund_account.id if fund_account else False,
            'project_expense_id': project_expense.id if project_expense else False,
            'state_before': state_before or '',
            'state_after': state_after or '',
        })