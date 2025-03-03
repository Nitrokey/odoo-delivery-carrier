# Copyright 2020 Hunki Enterprises BV
# Copyright 2021-2022 Tecnativa - Víctor Martínez
# Copyright 2024 Sygel - Manuel Regidor
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import Form, common
from .test_ups_insurance import TestDeliveryUpsInsurance
from ..models.ups_request import UpsRequest

_module_ns = "odoo.addons.delivery_ups_oca"
_provider_class = _module_ns + ".models.ups_request.UpsRequest"


class TestResidentialAddress(TestDeliveryUpsInsurance):
    @classmethod
    def setUpClass(self):
        super().setUpClass()
        self.company = self.env.ref("base.main_company")
        self.company.partner_id.write(
            {
                "phone": "+%s976123456" % self.company.country_id.phone_code,
            }
        )
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
            "type": "private",
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
        self.ups_request = UpsRequest(self.carrier)

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
        shipping_data = self.ups_request._partner_to_shipping_data(self.individual_partner)
        self.assertIn(
              "ResidentialAddressIndicator",
              shipping_data['Address'],
              "ResidentialAddressIndicator should be in shipping data"
          )

    def test_partner_to_shipping_data_commercial(self):
        shipping_data = self.ups_request._partner_to_shipping_data(self.company_partner)
        self.assertNotIn(
             "ResidentialAddressIndicator",
             shipping_data['Address'],
             "Commercial address should not contain ResidentialAddressIndicator"
         )
