import unittest
import mock
import os

from pyntc.devices.system_features.file_copy.eos_file_copy import EOSFileCopy

CURRNENT_DIR = os.path.dirname(os.path.realpath(__file__))

class TestEOSFileCopy(unittest.TestCase):


    @mock.patch('pyntc.devices.eos_device.EOSDevice', autospec=True)
    def setUp(self, mock_eos_device):
        self.mock_device = mock_eos_device.return_value
        self.eos_fc = EOSFileCopy(self.mock_device, os.path.join(CURRNENT_DIR, 'fixtures', 'test_file'))

    def test_init(self):
        self.assertEqual(self.eos_fc.remote, 'test_file')

    def test_get_remote_size(self):
        dir_out = 'Directory of flash:/\n\n       -rwx   211532893           Apr 27  2015  EOS.swi\n       -rwx          18           Feb 27  2015  boot-config\n       -rwx           0            Mar 7  2015  boot-extensions\n       drwx        4096            Mar 2  2015  debug\n       -rwx         499           May 18  2015  dhclient_override\n       -rwx         501            Feb 3 19:57  dhclient_override_example\n       drwx        4096           Apr 29  2015  jodys_ztp_tools\n       -rwx        5083           May 15  2015  jodys_ztp_tools.tgz\n       drwx        4096            Feb 3 20:01  persist\n       -rwx          59           Apr 29  2015  rc.eos\n       -rwx         735            Nov 2  2015  rollback-0\n       drwx        4096           Feb 28  2015  schedule\n       -rwx         825           Dec 30  2015  startup-config\n       -rwx          18           May 19  2015  system_mac_address\n       -rwx           0           May 19  2015  zerotouch-config\n\n2143281152 bytes total (1717510144 bytes free)\n'
        self.mock_device.show.return_value = dir_out

        expected = 1717510144
        result = self.eos_fc.get_remote_size()
        self.assertEqual(result, expected)

    def test_remote_file_exists(self):
        self.mock_device.show.return_value = 'response'
        result = self.eos_fc.remote_file_exists()
        self.assertTrue(result)

    def test_remote_file_not_exists(self):
        self.mock_device.show.side_effect = Exception
        result = self.eos_fc.remote_file_exists()
        self.assertFalse(result)

    def test_local_md5(self):
        result = self.eos_fc.get_local_md5()
        self.assertEqual(result, '386b5f9c494abc1fff70de21f6c42136')

    def test_remote_md5(self):
        self.mock_device.show.return_value = 'verify /md5 (EOS.swi) = d1389e46bbe1cd84f4de840621d36529\n'
        result = self.eos_fc.get_remote_md5()
        self.assertEqual(result, 'd1389e46bbe1cd84f4de840621d36529')

#    @mock.patch('paramiko.SSHClient', autospec=True)
#    @mock.patch('scp.SCPClient', autospec=True)
#    def test_transfer_file(self, mock_scp, mock_paramiko):
#        paramiko_instance = mock_paramiko.return_value
#        self.eos_fc.local_file_exists = mock.MagicMock()
#        self.eos_fc.enough_remote_space = mock.MagicMock()
#        self.mock_device.host = 'host'
#        self.mock_device.username = 'username'
#        self.mock_device.password = 'password'
#
#        self.eos_fc.transfer_file()
#        mock_scp.put.assert_called_with(self.eos_fc.local, self.eos_fc.remote)




if __name__ == "__main__":
    unittest.main()
