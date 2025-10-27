import base64
from unittest import mock

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


_module_ns = "odoo.addons.delivery_ups_oca"
_provider_class = _module_ns + ".ups_request.UpsRequest"


class TestSendPaperlessInvoice(TransactionCase):

    def setUp(self):
        super().setUp()

        # Create a dummy invoice PDF
        self.dummy_pdf = base64.b64encode(b"%PDF-1.4\n%Fake PDF Content\n%%EOF")

        product_shipping_cost = self.env["product.product"].create(
            {
                "type": "service",
                "name": "Shipping costs",
                "standard_price": 10,
                "list_price": 100,
            }
        )
        self.carrier = self.env["delivery.carrier"].create(
            {
                "name": "UPS",
                "delivery_type": "ups",
                "product_id": product_shipping_cost.id,
                "price_method": "fixed",
                "ups_default_packaging_id": self.env.ref(
                    "delivery_ups_oca.package_type_ups_02"
                ).id,
                "ups_package_dimension_code": "IN",
                "ups_package_weight_code": "LBS",
                "ups_service_code": "03",
                "ups_shipper_number": "123456",
                "ups_client_id": "dummy",
                "ups_client_secret": "dummy",
                "ups_file_format": "GIF",
                "country_groups": [(6, 0, [
                    self.env.ref('base.europe').id, self.env.ref('base.south_america').id,
                    self.env.ref('base.sepa_zone').id, self.env.ref('base.gulf_cooperation_council').id])],
            }
        )

        self.partner = self.env['res.partner'].create({
            'name': 'Test Partner',
        })

        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'product',
        })

        self.so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
        })

        self.env['sale.order.line'].create({
            'order_id': self.so.id,
            'product_id': self.product.id,
            'product_uom_qty': 1,
            'price_unit': 100.0,
        })

        self.so.action_confirm()
        self.picking = self.so.picking_ids[0]
        self.picking.move_lines.quantity_done = 10
        self.picking.carrier_id = self.carrier.id
        self.picking.action_assign()

        for move in self.picking.move_ids_without_package:
            move.quantity_done = move.product_uom_qty

        self.invoice = self.so._create_invoices()
        self.invoice.action_post()

    def test_prepare_paperless_invoice_provider_adds_missing_docs(self):
        result = self.carrier.prepare_paperless_invoice_provider(self.picking)
        doc_types = [doc['UserCreatedFormDocumentType'] for doc in result]
        self.assertIn("002", doc_types, "Invoice should be added if missing")
        self.assertIn("010", doc_types, "Packing list should be added if missing")

    def test_ups_paperless_invoice_raises_if_document_id_exists(self):
        """Should raise UserError when no document data is passed"""
        self.picking.document_id = 'DUMMY_ID'
        with self.assertRaises(UserError):
            self.carrier.ups_paperless_invoice_provider(self.picking)

    def test_prepare_paperless_invoice_raises_if_invoice_missing(self):
        self.picking.sale_id.invoice_ids = False
        with self.assertRaises(UserError):
            self.carrier.ups_paperless_invoice_provider(self.picking)

    def test_send_paperless_invoice_data(self):
        self.picking.ups_paperless_auto_send = True
        self.picking.ups_paperless_document = [
            (0, 0, {
                "file_name": 'Paperless Invoice - 001',
                "ups_document_type": '003',
                "ups_paperless_file": self.dummy_pdf,
            }),
            (0, 0, {
                "file_name": 'Paperless Invoice - 002',
                "ups_document_type": '013',
                "ups_paperless_file": self.dummy_pdf,
            })
        ]
        with mock.patch(
            _provider_class + ".send_paperless_invoice",
            return_value='DOC123456789'
        ):
            result = self.carrier.ups_paperless_invoice_provider(self.picking)
            self.assertIsNotNone(result)
