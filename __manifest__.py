# -*- coding: utf-8 -*-
{
    'name': "nn_fund_management",

    'summary': "This Fund management system where you can request for money and need to GM approval then MD approval then your proposal approved other-wise Rejected if double spending then money lock",

    'description': """
    1.Fund Accounts (bank, cash, other)
    2.Incoming Funds with unique transaction reference
    3.Fund Allocation to Projects / Expense Heads (GM + MD approval)
    4.Fund Requisitions with bill control
    5.Fund Transfers between Projects / Expense Heads
    6.Full audit history
    7.Double-spending prevention at every step
    ===============
    Future feature 
    8.Dashboard
    9.Notification
    10.Advanced Approval Rule
    """,

    'author': "Anayet Hasan Niloy",
    'website': "https://www.nnservices&engineeringltd.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'ERP',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
    ],
    # only loaded in demonstration mode
    # 'demo': [
    #     'demo/demo.xml',
    # ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}

