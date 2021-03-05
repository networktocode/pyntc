def test_show(iosxewlc_send_command):
    command = "show_ip_arp"
    device = iosxewlc_send_command([f"{command}.txt"])
    device.show(command)
    device.native.send_command.assert_called_with(command_string="show_ip_arp")
    device.native.send_command.assert_called_once()


def test_show_delay_factor(iosxewlc_send_command):
    command = "show_ip_arp"
    delay_factor = 20
    device = iosxewlc_send_command([f"{command}"])
    device.show(command, delay_factor=delay_factor)
    device.native.send_command.assert_called_with(command_string="show_ip_arp", delay_factor=delay_factor)
    device.native.send_command.assert_called_once()
