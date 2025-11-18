# Copyright 2020 Hunki Enterprises BV
# Copyright 2021-2022 Tecnativa - Víctor Martínez
# Copyright 2024 Sygel - Manuel Regidor
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
from unittest import mock

from odoo.tests import Form, common
from odoo.exceptions import UserError
from ..models.ups_request import UpsRequest

_module_ns = "odoo.addons.delivery_ups_oca"
_provider_class = _module_ns + ".models.ups_request.UpsRequest"


class TestDeliveryUpsBase(common.TransactionCase):
    @classmethod
    def setUpClass(self):
        super().setUpClass()
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
                    "delivery_ups_oca.product_packaging_ups_02"
                ).id,
                "ups_package_dimension_code": "IN",
                "ups_package_weight_code": "LBS",
                "ups_service_code": "03",
                "ups_shipper_number": "123456",
                "ups_client_id": "dummy",
                "ups_client_secret": "dummy",
                "ups_file_format": "GIF",
                "declared_amount_percentage": 80,
                "country_groups": [(6, 0, [
                    self.env.ref('base.europe').id,
                    self.env.ref('base.south_america').id,
                    self.env.ref('base.sepa_zone').id,
                    self.env.ref('base.gulf_cooperation_council').id])],
            }
        )
        self.company = self.env.ref("base.main_company")
        self.company.partner_id.write(
            {
                "phone": f"+{self.company.country_id.phone_code}976123456",
                "vat": f"{self.company.country_id.code}09915370R",
            }
        )
        self.partner = self.env["res.partner"].create(
            {
                "name": "Test partner",
                "country_id": self.company.country_id.id,
                "phone": self.company.partner_id.phone,
                "email": "test@odoo.com",
                "street": self.company.partner_id.street,
                "city": self.company.partner_id.city,
                "zip": self.company.partner_id.zip,
                "state_id": self.company.partner_id.state_id.id,
                "vat": self.company.partner_id.vat,
            }
        )
        self.product = self.env["product.product"].create(
            {
                "name": "Test product",
                "type": "consu",
                "is_storable": True,
                "weight": 10,
            }
        )
        self.sale = self._create_sale_order(self)
        self.picking = self.sale.picking_ids[0]

    def _create_sale_order(self):
        order_form = Form(self.env["sale.order"])
        order_form.partner_id = self.partner
        with order_form.order_line.new() as line_form:
            line_form.product_id = self.product
            line_form.product_uom_qty = 10
        sale = order_form.save()
        delivery_wizard = Form(
            self.env["choose.delivery.carrier"].with_context(
                **{"default_order_id": sale.id, "default_carrier_id": self.carrier.id}
            )
        ).save()
        delivery_wizard.button_confirm()
        sale.action_confirm()
        return sale


class TestDeliveryUps(TestDeliveryUpsBase):
    @classmethod
    def setUpClass(self):
        super().setUpClass()
        self.picking = self.sale.picking_ids[0]
        self.picking.move_ids.quantity = 10

    def test_order_ups_rate_shipment(self):
        with mock.patch(
            _provider_class + "._rate_shipment",
            return_value={
                "RateResponse": {
                    "RatedShipment": {
                        "TotalCharges": {"MonetaryValue": 1, "CurrencyCode": "USD"}
                    }
                }
            },
        ):
            res = self.carrier.ups_rate_shipment(self.sale)
            self.assertGreater(res["price"], 0)
            self.assertTrue(res["success"])

    def test_order_ups_rate_shipment_currency_extra(self):
        usd = self.env.ref("base.USD")
        eur = self.env.ref("base.EUR")
        currency = self.env.ref("base.main_company").currency_id
        currency_extra = eur if currency == usd else usd
        self.sale.currency_id = currency_extra
        with mock.patch(
            _provider_class + "._rate_shipment",
            return_value={
                "RateResponse": {
                    "RatedShipment": {
                        "TotalCharges": {"MonetaryValue": 1, "CurrencyCode": "USD"}
                    }
                }
            },
        ):
            res = self.carrier.ups_rate_shipment(self.sale)
            self.assertGreater(res["price"], 0)
            self.assertTrue(res["success"])

    def test_delivery_carrier_ups_integration(self):
        self.picking.action_confirm()
        self.picking.action_assign()
        # Create a simple PDF-like bytes object for testing
        label = b"%PDF-1.4\n%EOF"
        with mock.patch(
            _provider_class + "._send_shipping",
            return_value={
                "price": {"CurrencyCode": "USD", "MonetaryValue": "0.0"},
                "ShipmentIdentificationNumber": "123456",
                "labels": [
                    {
                        "tracking_ref": "123456",
                        "format_code": "png",
                        "datas": base64.b64encode(label),
                    }
                ],
            },
        ):
            self.picking.send_to_shipper()
            self.assertEqual(self.picking.message_attachment_count, 1)
            self.assertTrue(self.picking.carrier_tracking_ref)
            self.assertFalse(self.picking.tracking_state_history)
            self.assertEqual(
                self.picking.delivery_state, "shipping_recorded_in_carrier"
            )
            if self.picking.carrier_id.ups_tracking_state_update_sync:
                with mock.patch(
                    _provider_class + ".tracking_state_update",
                    return_value={
                        "delivery_state": "in_transit",
                        "tracking_state_history": "history",
                    },
                ):
                    self.picking.tracking_state_update()
                    self.assertEqual(self.picking.delivery_state, "in_transit")
                    self.assertTrue(self.picking.tracking_state_history)
            with mock.patch(
                _provider_class + ".cancel_shipment",
                return_value=True,
            ):
                self.picking.cancel_shipment()
                self.assertFalse(self.picking.carrier_tracking_ref)
                self.assertEqual(self.picking.delivery_state, "canceled_shipment")

    def check_insurance_packages(self, carrier, picking):
        ups_request = UpsRequest(carrier)
        vals = ups_request._prepare_create_shipping(picking)
        packages = vals["ShipmentRequest"]["Shipment"]["Package"]
        for package in packages:
            self.assertIn("PackageServiceOptions", package)
            self.assertIn("DeclaredValue", package["PackageServiceOptions"])
            self.assertEqual(
                package["PackageServiceOptions"]["DeclaredValue"]["MonetaryValue"],
                "8.0",
            )

    def test_insurance_with_packages(self):
        """Test that insurance is added when packages exist"""
        pack_action = self.picking.action_put_in_pack()
        pack_action_ctx = pack_action['context']
        pack_wiz = self.env['choose.delivery.package'].with_context(
            pack_action_ctx).create(
            {
                "delivery_package_type_id": self.carrier.ups_default_packaging_id.id})
        pack_wiz.action_put_in_pack()

        self.carrier.write({"ups_use_packages_from_picking": True})
        self.check_insurance_packages(self.carrier, self.picking)

    def test_insurance_without_packages(self):
        """Test insurance when no packages are defined"""
        self.picking.move_line_ids.write({"result_package_id": False})
        self.carrier.write({"ups_use_packages_from_picking": False})
        self.check_insurance_packages(self.carrier, self.picking)

    def test_insurance_without_packages_cod(self):
        """Test insurance when no packages are defined and COD option"""
        self.carrier.write({
            "ups_use_packages_from_picking": False,
            "ups_cash_on_delivery": True,
        })
        ups_request = UpsRequest(self.carrier)
        vals = ups_request._prepare_create_shipping(self.picking)
        shipment = vals["ShipmentRequest"]["Shipment"]
        self.assertIn("ShipmentServiceOptions", shipment)
        service_option = shipment["ShipmentServiceOptions"]
        self.assertIn("COD", service_option)
        self.assertEqual(
            service_option["COD"]["CODAmount"]["MonetaryValue"],
            "11.9"
        )


class TestSendPaperlessInvoice(TestDeliveryUpsBase):

    def setUp(self):
        super().setUp()
        self.picking = self.sale.picking_ids[0]
        self.picking.move_ids.quantity = 10
        self.picking.action_assign()

        # Create a dummy invoice PDF
        self.dummy_pdf = base64.b64encode(b"%PDF-1.4\n%Fake PDF Content\n%%EOF")

        self.invoice = self.sale._create_invoices()
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


class TestResidentialAddress(TestDeliveryUpsBase):
    @classmethod
    def setUpClass(self):
        super().setUpClass()
        # Base partner (parent company)
        self.company_partner = self.env["res.partner"].create({
            "name": "ABC Pvt Ltd",
            "is_company": True,
            "company_name": "ABC Pvt Ltd",
            "country_id": self.company.country_id.id,
            "phone": self.company.partner_id.phone,
            "email": "test123@odoo.com",
            "street": self.company.partner_id.street,
            "city": self.company.partner_id.city,
            "zip": self.company.partner_id.zip,
            "state_id": self.company.partner_id.state_id.id,
        })

        # Individual partner with no company
        self.individual_partner = self.env["res.partner"].create({
            "name": "John Doe",
            "is_company": False,
            "company_name": False,
            "street": "456 Housing Colony",
            "city": "Brussels",
            "state_id": self.company.partner_id.state_id.id,
            "zip": "12345",
            "country_id": self.company.country_id.id,
            "phone": "3454657",
            "email": "john@example.com",
        })
        self.private_partner = self.env["res.partner"].create({
            "name": "John Doe",
            "type": "other",
            "is_company": False,
            "company_name": False,
            "street": "456 Housing Colony",
            "city": "Brussels",
            "state_id": self.company.partner_id.state_id.id,
            "zip": "12345",
            "country_id": self.company.country_id.id,
            "phone": "3454657",
            "email": "john@example.com",
        })

    def test_is_residential_address_individual(self):
        self.assertTrue(
            self.individual_partner._is_residential_address(),
            "Individual with no company should be residential"
        )

    def test_is_residential_address_private_type(self):
        self.assertTrue(
            self.private_partner._is_residential_address(),
            "Partner of type 'private' should be residential"
        )

    def test_is_residential_address_commercial(self):
        self.assertFalse(
            self.company_partner._is_residential_address(),
            "Company partner should not be residential"
        )

    def test_partner_to_shipping_data_contains_residential(self):
        ups_request = UpsRequest(self.carrier)
        shipping_data = ups_request._partner_to_shipping_data(
            self.individual_partner)
        self.assertIn(
            "ResidentialAddressIndicator",
            shipping_data['Address'],
            "ResidentialAddressIndicator should be in shipping data"
        )

    def test_partner_to_shipping_data_commercial(self):
        ups_request = UpsRequest(self.carrier)
        shipping_data = ups_request._partner_to_shipping_data(self.company_partner)
        self.assertNotIn(
            "ResidentialAddressIndicator",
            shipping_data['Address'],
            "Commercial address should not contain ResidentialAddressIndicator"
        )


class TestDeliveryUpsPhone(TestDeliveryUpsBase):

    def test_partner_to_shipping_data_without_phone(self):
        """Test that phone field is omitted when partner has no phone number"""

        ups_request = UpsRequest(self.carrier)

        # Test partner with phone number - should include Phone field
        shipping_data_with_phone = ups_request._partner_to_shipping_data(
            self.partner
        )
        self.assertIn("Phone", shipping_data_with_phone)
        self.assertEqual(
            shipping_data_with_phone["Phone"]["Number"], self.partner.phone
        )

        # Test partner without phone number - should omit Phone field
        self.partner.write({"phone": None})
        shipping_data_no_phone = ups_request._partner_to_shipping_data(
            self.partner
        )
        self.assertNotIn("Phone", shipping_data_no_phone)

        # Test partner without phone number and with mobile number
        self.partner.write({"phone": None, "mobile": 123456})
        shipping_data_no_phone = ups_request._partner_to_shipping_data(
            self.partner
        )
        self.assertIn("Phone", shipping_data_no_phone)

        # Verify other fields are still present
        self.assertIn("Name", shipping_data_no_phone)
        self.assertIn("AttentionName", shipping_data_no_phone)
        self.assertIn("EMailAddress", shipping_data_no_phone)
        self.assertIn("Address", shipping_data_no_phone)
