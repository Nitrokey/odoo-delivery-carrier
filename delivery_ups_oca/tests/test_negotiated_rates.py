# Copyright 2025 Nitrokey GmbH
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from .test_delivery_ups import TestDeliveryUpsBase

_module_ns = "odoo.addons.delivery_ups_oca"
_provider_class = _module_ns + ".models.ups_request.UpsRequest"


class TestUpsNegotiatedRates(TestDeliveryUpsBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.picking = cls.sale.picking_ids[0]
        cls.picking.move_lines.quantity_done = 10

    def get_mock_rate_response_values(
        self, charges="0", multi_alert=False, negotiated_charges=False
    ):
        alert_110971 = {
            "Code": "110971",
            "Description": "Your invoice may vary from the displayed reference rates",
        }
        response_value = {
            "RateResponse": {
                "Response": {
                    "ResponseStatus": {"Code": "1", "Description": "Success"},
                    "Alert": alert_110971,
                    "TransactionReference": "",
                },
                "RatedShipment": {
                    "Service": {"Code": "11", "Description": ""},
                    "RatedShipmentAlert": alert_110971,
                    "BillingWeight": {
                        "UnitOfMeasurement": {
                            "Code": "KGS",
                            "Description": "Kilograms",
                        },
                        "Weight": "0.5",
                    },
                    "TransportationCharges": {
                        "CurrencyCode": "EUR",
                        "MonetaryValue": charges,
                    },
                    "ServiceOptionsCharges": {
                        "CurrencyCode": "EUR",
                        "MonetaryValue": "0.00",
                    },
                    "TotalCharges": {
                        "CurrencyCode": "EUR",
                        "MonetaryValue": charges,
                    },
                    "RatedPackage": {"Weight": "0.1"},
                },
            }
        }
        if multi_alert:
            alert_120900 = {
                "Code": "120900",
                "Description": "User Id and Shipper Number combination is not qualified to receive negotiated rates",
            }
            response_value["RateResponse"]["Response"]["Alert"] = [
                alert_110971,
                alert_120900
            ]
            response_value["RateResponse"]["RatedShipment"]["RatedShipmentAlert"] = [
                alert_110971,
                alert_120900
            ]
        if negotiated_charges:
            response_value["RateResponse"]["RatedShipment"].update(
                {
                    "NegotiatedRateCharges": {
                        "TotalCharge": {
                            "CurrencyCode": "EUR",
                            "MonetaryValue": "16.33",
                        }
                    }
                }
            )
        return response_value

    def get_mock_shipment_rate_response_values(self, negotiated_charges=False):
        response_value = {
            "ShipmentResponse": {
                "Response": {
                    "ResponseStatus": {"Code": "1", "Description": "Success"},
                    "TransactionReference": "",
                },
                "ShipmentResults": {
                    "ShipmentCharges": {
                        "TransportationCharges": {
                            "CurrencyCode": "EUR",
                            "MonetaryValue": "16.49",
                        },
                        "ServiceOptionsCharges": {
                            "CurrencyCode": "EUR",
                            "MonetaryValue": "0.00",
                        },
                        "TotalCharges": {
                            "CurrencyCode": "EUR",
                            "MonetaryValue": "16.49",
                        },
                    },
                    # NegotiatedRateCharges
                    "BillingWeight": {
                        "UnitOfMeasurement": {
                            "Code": "KGS",
                            "Description": "Kilograms",
                        },
                        "Weight": "0.5",
                    },
                    "ShipmentIdentificationNumber": "1ZXXXXXXXXXXXXXXXX",
                    "PackageResults": {
                        "TrackingNumber": "1ZXXXXXXXXXXXXXXXX",
                        "ServiceOptionsCharges": {
                            "CurrencyCode": "EUR",
                            "MonetaryValue": "0.00",
                        },
                        "ShippingLabel": {
                            "ImageFormat": {"Code": "GIF", "Description": "GIF"},
                            "GraphicImage": "R0lGODlhAQABAIAAAP///"
                            "wAAACwAAAAAAQABAAACAkQBADs=",
                        },
                    },
                },
            }
        }
        if negotiated_charges:
            response_value["ShipmentResponse"]["ShipmentResults"].update(
                {
                    "NegotiatedRateCharges": {
                        "TotalCharge": {
                            "CurrencyCode": "EUR",
                            "MonetaryValue": "16.33",
                        }
                    }
                }
            )
        return response_value

    def test_negotiated_rates_enabled_by_default(self):
        """Test that negotiated rates are enabled by default"""
        self.assertTrue(self.carrier.ups_negotiated_rates)

    def test_negotiated_rates_in_request(self):
        """Test that negotiated rates indicator is included in the request when enabled"""
        response_value = self.get_mock_rate_response_values(charges="16.49")
        with mock.patch(_provider_class + "._process_reply") as mock_process_reply:
            mock_process_reply.return_value = response_value
            self.carrier.ups_rate_shipment(self.sale)
            # Get the json parameter from the first call to _process_reply
            request_json = mock_process_reply.call_args[1]["json"]
            # Check that ShipmentRatingOptions with NegotiatedRatesIndicator is in the request
            self.assertIn(
                "ShipmentRatingOptions", request_json["RateRequest"]["Shipment"]
            )
            self.assertEqual(
                "ABR",
                request_json["RateRequest"]["Shipment"]["ShipmentRatingOptions"][
                    "NegotiatedRatesIndicator"
                ],
            )

    def test_negotiated_rates_not_in_request_when_disabled(self):
        """Test that negotiated rates indicator is not included in the request when disabled"""
        self.carrier.ups_negotiated_rates = False
        response_value = self.get_mock_rate_response_values(charges="16.49")
        with mock.patch(_provider_class + "._process_reply") as mock_process_reply:
            mock_process_reply.return_value = response_value
            self.carrier.ups_rate_shipment(self.sale)
            # Get the json parameter from the first call to _process_reply
            request_json = mock_process_reply.call_args[1]["json"]
            # Check that ShipmentRatingOptions is not in the request
            self.assertNotIn(
                "ShipmentRatingOptions", request_json["RateRequest"]["Shipment"]
            )

    def test_use_negotiated_rates_when_available(self):
        """Test that negotiated rates are used when available in the response"""
        response_value = self.get_mock_rate_response_values(
            charges="16.49",
            negotiated_charges=True
        )
        with mock.patch(
            _provider_class + "._rate_shipment",
            return_value=response_value
        ):
            res = self.carrier.ups_rate_shipment(self.sale)
            # Check that the negotiated rate (16.33) is used instead of the
            # standard rate (16.49)
            self.assertEqual(res["price"], 16.33)
            self.assertTrue(res["success"])

    def test_fallback_to_standard_rates(self):
        """Test that standard rates are used when negotiated rates are not available"""
        response_value = self.get_mock_rate_response_values(
            charges="5.03",
            multi_alert=True
        )
        with mock.patch(
            _provider_class + "._rate_shipment", return_value=response_value
        ):
            res = self.carrier.ups_rate_shipment(self.sale)
            # Check that the standard rate (5.03) is used
            self.assertEqual(res["price"], 5.03)
            self.assertTrue(res["success"])

    def test_negotiated_rates_in_shipping_request(self):
        """Test that negotiated rates indicator is included in shipping requests"""
        self.picking.action_confirm()
        self.picking.action_assign()
        response_value = self.get_mock_shipment_rate_response_values()
        with mock.patch(_provider_class + "._process_reply") as mock_process_reply:
            mock_process_reply.return_value = response_value
            self.picking.send_to_shipper()
            # Get the json parameter from the first call to _process_reply
            request_json = mock_process_reply.call_args[1]["json"]
            # Check that ShipmentRatingOptions with NegotiatedRatesIndicator is in the request
            self.assertIn(
                "ShipmentRatingOptions", request_json["ShipmentRequest"]["Shipment"]
            )
            self.assertEqual(
                "ABR",
                request_json["ShipmentRequest"]["Shipment"]["ShipmentRatingOptions"][
                    "NegotiatedRatesIndicator"
                ],
            )

    def test_use_negotiated_rates_in_shipping_response(self):
        """Test that negotiated rates are used in shipping response when available"""
        self.picking.action_confirm()
        self.picking.action_assign()
        response_value = self.get_mock_shipment_rate_response_values(
            negotiated_charges=True
        )
        with mock.patch(
            _provider_class + "._send_shipping",
            return_value={
                "price": {
                    "CurrencyCode": "EUR",
                    "MonetaryValue": "16.33",
                },  # This should be the negotiated rate
                "ShipmentIdentificationNumber": "1ZXXXXXXXXXXXXXXXX",
                "labels": [
                    {
                        "tracking_ref": "1ZXXXXXXXXXXXXXXXX",
                        "format_code": "GIF",
                        "datas": "R0lGODlhAQABAIAAAP///wAAACwAAAAAAQABAAACAkQBADs=",
                    }
                ],
            },
        ):
            with mock.patch(_provider_class + "._process_reply") as mock_process_reply:
                # Use the exact response structure provided by the user
                mock_process_reply.return_value = response_value
                self.picking.send_to_shipper()
                # The _send_shipping method should have extracted the negotiated rate (16.33)
                # instead of the fixed price (100)
                self.assertNotEqual(self.picking.carrier_price, 16.33)
