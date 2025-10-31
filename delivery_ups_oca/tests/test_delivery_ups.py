# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
from unittest import mock

from odoo.tests import Form, common

_module_ns = "odoo.addons.delivery_ups_oca"
_provider_class = _module_ns + ".models.ups_request.UpsRequest"


class TestDeliveryUpsBase(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product_shipping_cost = cls.env["product.product"].create(
            {
                "type": "service",
                "name": "Shipping costs",
                "standard_price": 10,
                "list_price": 100,
            }
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "UPS",
                "delivery_type": "ups",
                "product_id": product_shipping_cost.id,
                "price_method": "fixed",
                "ups_default_packaging_id": cls.env.ref(
                    "delivery_ups_oca.product_packaging_ups_02"
                ).id,
                "ups_shipper_number": "123456",
                "ups_service_code": "11",
                "ups_file_format": "GIF",
                "ups_tracking_state_update_sync": True,
                "ups_client_id": "test_client_id",
                "ups_client_secret": "test_client_secret",
            }
        )
        cls.company = cls.env.ref("base.main_company")
        cls.company.partner_id.write(
            {
                "phone": f"+{cls.company.country_id.phone_code}976123456",
                "vat": f"{cls.company.country_id.code}09915370R",
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test partner",
                "country_id": cls.company.country_id.id,
                "phone": cls.company.partner_id.phone,
                "email": "test@odoo.com",
                "street": cls.company.partner_id.street,
                "city": cls.company.partner_id.city,
                "zip": cls.company.partner_id.zip,
                "state_id": cls.company.partner_id.state_id.id,
                "vat": cls.company.partner_id.vat,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Test product",
                "type": "consu",
                "is_storable": True,
                "weight": 10,
            }
        )
        cls.sale = cls._create_sale_order(cls)

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
    def setUpClass(cls):
        super().setUpClass()
        cls.picking = cls.sale.picking_ids[0]
        cls.picking.move_ids.quantity = 10

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

    def test_ups_create_shipping(self):
        label = b"%PDF-1.4\n%EOF"
        with mock.patch(
            _provider_class + "._send_shipping",
            return_value={
                "price": {"CurrencyCode": "USD", "MonetaryValue": "10.0"},
                "ShipmentIdentificationNumber": "123456",
                "labels": [
                    {
                        "tracking_ref": "123456",
                        "format_code": "GIF",
                        "datas": base64.b64encode(label),
                    }
                ],
            },
        ):
            result = self.carrier.ups_create_shipping(self.picking)
            self.assertEqual(result["tracking_number"], "123456")
            self.assertEqual(result["exact_price"], 10.0)
            self.assertEqual(self.picking.carrier_tracking_ref, "123456")

    def test_ups_send_shipping(self):
        label = b"%PDF-1.4\n%EOF"
        with mock.patch(
            _provider_class + "._send_shipping",
            return_value={
                "price": {"CurrencyCode": "USD", "MonetaryValue": "10.0"},
                "ShipmentIdentificationNumber": "123456",
                "labels": [
                    {
                        "tracking_ref": "123456",
                        "format_code": "GIF",
                        "datas": base64.b64encode(label),
                    }
                ],
            },
        ):
            results = self.carrier.ups_send_shipping(self.picking)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["tracking_number"], "123456")

    def test_ups_get_label(self):
        label = b"%PDF-1.4\n%EOF"
        self.picking.carrier_tracking_ref = "123456"
        with mock.patch(
            _provider_class + ".shipping_label",
            return_value=[
                {
                    "tracking_ref": "123456",
                    "format_code": "GIF",
                    "datas": base64.b64encode(label),
                }
            ],
        ):
            attachments = self.carrier.ups_get_label("123456")
            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments.name, "123456-GIF.GIF")

    def test_ups_get_label_no_tracking_ref(self):
        result = self.carrier.ups_get_label(False)
        self.assertFalse(result)

    def test_ups_get_tracking_link(self):
        self.picking.carrier_tracking_ref = "123456"
        tracking_link = self.carrier.ups_get_tracking_link(self.picking)
        expected_link = "https://ups.com/WebTracking/track?trackingNumber=123456"
        self.assertEqual(tracking_link, expected_link)

    def test_ups_cancel_shipment(self):
        self.picking.carrier_tracking_ref = "123456"
        with mock.patch(
            _provider_class + ".cancel_shipment",
            return_value=True,
        ):
            result = self.carrier.ups_cancel_shipment(self.picking)
            self.assertTrue(result)

    def test_ups_tracking_state_update(self):
        self.picking.carrier_tracking_ref = "123456"
        with mock.patch(
            _provider_class + ".tracking_state_update",
            return_value={
                "delivery_state": "in_transit",
                "tracking_state_history": "Test history",
            },
        ):
            self.carrier.ups_tracking_state_update(self.picking)
            self.assertEqual(self.picking.delivery_state, "in_transit")
            self.assertEqual(self.picking.tracking_state_history, "Test history")

    def test_ups_tracking_state_update_no_sync(self):
        self.carrier.ups_tracking_state_update_sync = False
        self.picking.carrier_tracking_ref = "123456"
        self.carrier.ups_tracking_state_update(self.picking)
        # Should do nothing when sync is disabled

    def test_ups_tracking_state_update_no_tracking_ref(self):
        self.picking.carrier_tracking_ref = False
        self.carrier.ups_tracking_state_update(self.picking)
        # Should do nothing when no tracking reference

    def test_picking_ups_get_label(self):
        label = b"%PDF-1.4\n%EOF"
        self.picking.carrier_tracking_ref = "123456"
        with mock.patch(
            _provider_class + ".shipping_label",
            return_value=[
                {
                    "tracking_ref": "123456",
                    "format_code": "GIF",
                    "datas": base64.b64encode(label),
                }
            ],
        ):
            result = self.picking.ups_get_label()
            self.assertIsNotNone(result)

    def test_picking_ups_get_label_wrong_carrier(self):
        self.picking.carrier_id.delivery_type = "fixed"
        self.picking.carrier_tracking_ref = "123456"
        result = self.picking.ups_get_label()
        self.assertIsNone(result)

    def test_picking_ups_get_label_no_tracking(self):
        self.picking.carrier_tracking_ref = False
        result = self.picking.ups_get_label()
        self.assertIsNone(result)

    def test_ups_rate_shipment_with_packages(self):
        # Test with packages from picking
        self.carrier.ups_use_packages_from_picking = True
        package = self.env["stock.quant.package"].create(
            {
                "name": "Test Package",
                "shipping_weight": 5,
            }
        )
        self.picking.move_line_ids.result_package_id = package.id

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

    def test_ups_rate_shipment_cash_on_delivery(self):
        # Test with cash on delivery
        self.carrier.ups_cash_on_delivery = True
        self.carrier.ups_cod_funds_code = "1"

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

    def test_ups_create_shipping_with_packages(self):
        # Test shipping creation with packages
        self.carrier.ups_use_packages_from_picking = True
        package = self.env["stock.quant.package"].create(
            {
                "name": "Test Package",
                "shipping_weight": 5,
            }
        )
        self.picking.move_line_ids.result_package_id = package.id

        label = b"%PDF-1.4\n%EOF"
        with mock.patch(
            _provider_class + "._send_shipping",
            return_value={
                "price": {"CurrencyCode": "USD", "MonetaryValue": "10.0"},
                "ShipmentIdentificationNumber": "123456",
                "labels": [
                    {
                        "tracking_ref": "123456",
                        "format_code": "GIF",
                        "datas": base64.b64encode(label),
                    }
                ],
            },
        ):
            result = self.carrier.ups_create_shipping(self.picking)
            self.assertEqual(result["tracking_number"], "123456")

    def test_ups_label_attachment_preparation(self):
        # Test label attachment preparation
        picking = self.picking
        values = {
            "name": "test_label.GIF",
            "datas": base64.b64encode(b"test"),
        }
        attachment_data = self.carrier._prepare_ups_label_attachment(picking, values)
        self.assertEqual(attachment_data["name"], "test_label.GIF")
        self.assertEqual(attachment_data["res_model"], picking._name)
        self.assertEqual(attachment_data["res_id"], picking.id)

    def test_ups_create_label_multiple_labels(self):
        # Test creating multiple labels
        label = b"%PDF-1.4\n%EOF"
        labels = [
            {
                "tracking_ref": "123456",
                "format_code": "GIF",
                "datas": base64.b64encode(label),
            },
            {
                "tracking_ref": "789012",
                "format_code": "ZPL",
                "datas": base64.b64encode(label),
            },
        ]
        attachments = self.carrier._create_ups_label(self.picking, labels)
        self.assertEqual(len(attachments), 2)
        self.assertEqual(attachments[0].name, "123456-GIF.GIF")
        self.assertEqual(attachments[1].name, "789012-ZPL.ZPL")
