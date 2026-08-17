import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
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

    def test_matrix_is_binary_safe_and_contains_required_byte_classes(self):
        self.assertEqual(MODULE.MATRIX_BYTES[0], 0)
        self.assertEqual(MODULE.MATRIX_BYTES[-1], 0xDA)
        self.assertIn(bytes.fromhex("1B 5B 33 31 6D"), MODULE.MATRIX_BYTES)
        self.assertIn(bytes.fromhex("B3 C4 DA"), MODULE.MATRIX_BYTES)
        self.assertIn(bytes.fromhex("0D 0A"), MODULE.MATRIX_BYTES)

    def test_exchange_evidence_is_byte_exact(self):
        output = io.StringIO()
        with redirect_stdout(output):
            MODULE.print_exchange_evidence(
                bytes.fromhex("00 41 FF"),
                bytes.fromhex("00 41 FF"),
                {"RX": "0041FF", "TX": "0041FF", "RESULT": "PASS"},
            )
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "HOST_TX_LENGTH=3",
                "HOST_TX_HEX=0041FF",
                "HOST_RX_LENGTH=3",
                "HOST_RX_HEX=0041FF",
                "GUEST_RX=0041FF",
                "GUEST_TX=0041FF",
                "GUEST_RESULT=PASS",
            ],
        )

    def test_exchange_is_distinct_from_serial_free_selftest(self):
        source = (Path(__file__).parents[1] / "qualification" / "serialtest.asm").read_text()
        self.assertIn("selftest:", source)
        self.assertIn("test ah, 01h", source.lower())
        self.assertIn("serial_ready_msg", source)


if __name__ == "__main__":
    unittest.main()
