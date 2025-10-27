# Copyright 2020 Hunki Enterprises BV
# Copyright 2021-2022 Tecnativa - Víctor Martínez
# Copyright 2024 Sygel - Manuel Regidor
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import Form, common
from ..ups_request import UpsRequest

_module_ns = "odoo.addons.delivery_ups_oca"
_provider_class = _module_ns + ".ups_request.UpsRequest"


class TestDeliveryUpsInsurance(common.TransactionCase):

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
                    "delivery_ups_oca.package_type_ups_02"
                ).id,
                "ups_package_dimension_code": "IN",
                "ups_package_weight_code": "LBS",
                "ups_service_code": "03",
                "ups_shipper_number": "123456",
                "ups_client_id": "dummy",
                "ups_client_secret": "dummy",
                "ups_file_format": "GIF",
                "declared_amount_percentage": 80,
            }
        )
        self.company = self.env.ref("base.main_company")
        self.company.partner_id.write(
            {
                "phone": "+%s976123456" % self.company.country_id.phone_code,
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
            }
        )
        self.product = self.env["product.product"].create(
            {"name": "Test product", "type": "product", "weight": 10}
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
                default_order_id=sale.id,
                default_carrier_id=self.carrier.id,
            )
        ).save()
        delivery_wizard.button_confirm()
        sale.action_confirm()
        return sale

    def check_insurance_packages(self, carrier, picking):
        ups_request = UpsRequest(carrier)
        vals = ups_request._prepare_create_shipping(picking)
        packages = vals["ShipmentRequest"]["Shipment"]["Package"]
        for package in packages:
            self.assertIn("PackageServiceOptions", package)
            self.assertIn("DeclaredValue", package["PackageServiceOptions"])
            self.assertEqual(
                package["PackageServiceOptions"]["DeclaredValue"]["MonetaryValue"],
                "10.0",
            )

    def test_insurance_with_packages(self):
        """Test that insurance is added when packages exist"""
        reusable_box = self.env["stock.quant.package"].create(
            {
                "name": "Reusable Box",
                "package_use": "reusable",
            }
        )
        self.picking.package_ids = [(6, 0, reusable_box.ids)]
        self.carrier.write({"ups_use_packages_from_picking": True})
        self.check_insurance_packages(
            self.carrier, self.picking
        )

    def test_insurance_without_packages(self):
        """Test insurance when no packages are defined"""
        self.picking.package_ids = [(6, 0, [])]
        self.carrier.write({"ups_use_packages_from_picking": False})
        self.check_insurance_packages(
            self.carrier, self.picking
        )

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
