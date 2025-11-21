import unittest

from src.utils.system_parsers import (
    parse_netsh_interfaces,
    select_wireless_interface,
    parse_netsh_wlan_interfaces,
    parse_pnp_bluetooth_devices,
    select_primary_bluetooth_device,
    parse_powercfg_plans,
)


class SystemParserTests(unittest.TestCase):
    def test_parse_netsh_interfaces_and_select_wifi(self):
        output = """
Admin State    State          Type             Interface Name
-------------------------------------------------------------------------
Enabled        Connected      Dedicated        Ethernet
Enabled        Connected      Dedicated        Wi-Fi
Disabled       Disconnected   Dedicated        Ethernet 2
"""
        interfaces = parse_netsh_interfaces(output)
        wifi = select_wireless_interface(interfaces)
        self.assertIsNotNone(wifi)
        self.assertEqual(wifi["name"], "Wi-Fi")

    def test_parse_netsh_wlan_interfaces(self):
        output = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wireless
    GUID                   : abc
    Physical address       : 00:11:22
    State                  : connected
    SSID                   : HomeNetwork

"""
        interfaces = parse_netsh_wlan_interfaces(output)
        self.assertEqual(len(interfaces), 1)
        self.assertEqual(interfaces[0]["name"], "Wi-Fi")
        self.assertEqual(interfaces[0]["ssid"], "HomeNetwork")

    def test_parse_pnp_devices_and_select_primary(self):
        output = """
Status           : OK
Class            : Bluetooth
InstanceId       : USB\\VID_1234
FriendlyName     : Intel(R) Wireless Bluetooth(R)

Status           : Error
Class            : Bluetooth
InstanceId       : USB\\VID_BAD
FriendlyName     : Some Other Device
"""
        devices = parse_pnp_bluetooth_devices(output)
        primary = select_primary_bluetooth_device(devices)
        self.assertIsNotNone(primary)
        self.assertIn("Intel", primary.get("friendlyname", ""))

    def test_parse_powercfg_plans(self):
        output = """
Existing Power Schemes (* Active)
-----------------------------------
Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *
Power Scheme GUID: a1841308-3541-4fab-bc81-f71556f20b4a  (Power saver)
"""
        plans = parse_powercfg_plans(output)
        self.assertEqual(len(plans), 2)
        names = {plan["name"].lower() for plan in plans}
        self.assertIn("balanced", names)
        self.assertIn("power saver", names)


if __name__ == "__main__":
    unittest.main()
