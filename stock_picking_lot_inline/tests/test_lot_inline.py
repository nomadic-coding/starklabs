# Copyright 2026 STARK LABS
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0).

from lxml import etree

from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLotInline(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id += cls.env.ref('stock.group_production_lot')
        cls.stock_location = cls.env.ref('stock.stock_location_stock')
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        cls.product = cls.env['product.product'].create({
            'name': 'Serial Product',
            'is_storable': True,
            'tracking': 'serial',
        })
        cls.sn1, cls.sn2 = cls.env['stock.lot'].create([
            {'name': 'SN-1', 'product_id': cls.product.id},
            {'name': 'SN-2', 'product_id': cls.product.id},
        ])
        for serial in cls.sn1 | cls.sn2:
            cls.env['stock.quant']._update_available_quantity(cls.product, cls.stock_location, 1, lot_id=serial)
        cls.picking = cls.env['stock.picking'].create({
            'picking_type_id': cls.env.ref('stock.picking_type_out').id,
            'location_id': cls.stock_location.id,
            'location_dest_id': cls.customer_location.id,
            'move_ids': [Command.create({
                'name': cls.product.name,
                'product_id': cls.product.id,
                'product_uom_qty': 1,
                'product_uom': cls.product.uom_id.id,
                'location_id': cls.stock_location.id,
                'location_dest_id': cls.customer_location.id,
            })],
        })
        cls.picking.action_confirm()
        cls.picking.action_assign()

    def _arch_field(self, model, view_xmlid, xpath):
        view = self.env.ref(view_xmlid)
        arch = self.env[model].get_view(view.id)['arch']
        return etree.fromstring(arch).xpath(xpath)[0]

    def test_operations_serial_column_shown_by_default(self):
        field = self._arch_field(
            'stock.picking', 'stock.view_picking_form',
            "//field[@name='move_ids_without_package']/list/field[@name='lot_ids']")
        self.assertEqual(field.get('optional'), 'show')

    def test_details_popup_lot_column_visible_on_delivery(self):
        move = self.picking.move_ids
        self.assertTrue(move.show_quant, "Deliveries use the 'Pick From' column")
        field = self._arch_field(
            'stock.move.line', 'stock.view_stock_move_line_operation_tree', "//field[@name='lot_id']")
        self.assertEqual(
            field.get('column_invisible'),
            "parent.has_tracking == 'none' or not parent.show_lots_m2o and not parent.show_quant")

    def test_set_serial_from_details_popup(self):
        move = self.picking.move_ids
        other = self.sn2 if move.move_line_ids.lot_id == self.sn1 else self.sn1
        with Form(move, view='stock.view_stock_move_operations') as move_form:
            with move_form.move_line_ids.edit(0) as line:
                line.lot_id = other
        self.assertEqual(move.move_line_ids.lot_id, other)
        self.assertEqual(move.quantity, 1)
        reserved = self.env['stock.quant'].search([
            ('product_id', '=', self.product.id), ('reserved_quantity', '>', 0)])
        self.assertEqual(reserved.lot_id, other)
