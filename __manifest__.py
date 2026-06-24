# -*- coding: utf-8 -*-
{
    'name': "nn_fund_management",

    'summary': "This Fund management system where you can request for money and need to GM approval then MD approval then your proposal approved other-wise Rejected if double spending then money lock",

    'description': """
    nn_fund_management
    ==================
    1.Fund Accounts (bank, cash, other)
    2.Incoming Funds with unique transaction reference
    3.Fund Allocation to Projects / Expense Heads (GM + MD approval)
    4.Fund Requisitions with bill control
    5.Fund Transfers between Projects / Expense Heads
    6.Full audit history
    7.Double-spending prevention at every step
    8.Full immutable approval audit history
    
    ===============
    Future feature 
    1.Dashboard with charts
    2.Email or Bank notification integration
    3.odoo activity or notification system
    4.Configurable approval rules by amount range
    5.Automated tests (tests or folder)
    """,

    'author': "Anayet Hasan Niloy",
    'website': "https://www.nnservices&engineeringltd.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Finance',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'mail', 'account'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'security/security.xml',
        'security/record_rules.xml',
        'security/ir.model.access.csv',
        
        # Sequences
        'data/sequences.xml',
        
        # Views
        'views/fund_account_views.xml',
        'views/incoming_fund_views.xml',
        'views/project_expense_views.xml',
        'views/approval_history_views.xml',
        'views/fund_allocation_views.xml',
        'views/fund_requisition_views.xml',
        'views/fund_transfer_views.xml',
        'views/fund_bill_views.xml',
        'views/menu.xml',
    ],
    # only loaded in demonstration mode
    # 'demo': [
    #     'demo/demo.xml',
    # ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}

