# -*- coding: utf-8 -*-
# from odoo import http


# class NnFundManagement(http.Controller):
#     @http.route('/nn_fund_management/nn_fund_management', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/nn_fund_management/nn_fund_management/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('nn_fund_management.listing', {
#             'root': '/nn_fund_management/nn_fund_management',
#             'objects': http.request.env['nn_fund_management.nn_fund_management'].search([]),
#         })

#     @http.route('/nn_fund_management/nn_fund_management/objects/<model("nn_fund_management.nn_fund_management"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('nn_fund_management.object', {
#             'object': obj
#         })

