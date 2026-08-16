import importlib.util
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "ubb_dos_serial_qualify", Path(__file__).parents[1] / "scripts" / "ubb-dos-serial-qualify.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DOSSerialQualificationTests(unittest.TestCase):
    def test_result_parser_preserves_bytes_as_hex(self):
        with tempfile.TemporaryDirectory() as temp:
            result = Path(temp) / "SERIAL.RESULT"
            result.write_text("RX=00010AB3C4DAFF\nRESULT=PASS\n", encoding="ascii")
            parsed = MODULE.parse_result(result)
        self.assertEqual(parsed["RX"], "00010AB3C4DAFF")
        self.assertEqual(parsed["RESULT"], "PASS")

    def test_boot_files_are_noninteractive_and_network_is_not_enabled(self):
        with tempfile.TemporaryDirectory() as temp:
            drive = Path(temp) / "drive_c"
            (drive / "FREEDOS" / "BIN").mkdir(parents=True)
            (drive / "FREEDOS" / "BIN" / "COMMAND.COM").write_bytes(b"command")
            serial = Path(temp) / "SERIALTEST.COM"
            serial.write_bytes(b"dos-test")
            MODULE.install_boot_files(drive, serial)
            autoexec = (drive / "AUTOEXEC.BAT").read_text()
            config = (drive / "FDCONFIG.SYS").read_text()
        self.assertIn("UBBTEST.COM EXCHANGE", autoexec)
        self.assertNotIn("CTTY", autoexec.upper())
        self.assertIn("SHELL=", config)
        self.assertLessEqual(len("UBBTEST"), 8)
        self.assertLessEqual(len("SERIAL"), 8)

    def test_expected_exchange_is_bytes(self):
        self.assertEqual(MODULE.EXPECTED_RX, bytes((0x41, 0x42, 0x43)))
        self.assertEqual(MODULE.EXPECTED_TX, bytes.fromhex("55 42 42 2D 4F 4B"))


if __name__ == "__main__":
    unittest.main()
