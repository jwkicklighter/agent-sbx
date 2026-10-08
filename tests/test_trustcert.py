"""`sbx import-sandbox-ca`: fetch a sandbox's certificate and trust it."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sbxlib import cli, trustcert
from sbxlib.run import CommandError, Result, Runner
from tests.test_cli import FakeApi

PEM = "-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIUabc123\n-----END CERTIFICATE-----\n"


class ParseTest(unittest.TestCase):
    def test_takes_the_first_certificate(self):
        self.assertEqual(trustcert.parse("junk\n" + PEM + PEM), PEM)

    def test_text_without_a_certificate_is_refused(self):
        with self.assertRaises(trustcert.TrustError):
            trustcert.parse("cat: /etc/sbx/tls/cert.pem: No such file")


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "anchors").mkdir()
        self.stores = ((self.tmp / "anchors", ["update-ca-trust"]),)

    def run_install(self, certutil):
        runner = Runner(responder=lambda a, d: "")
        with mock.patch.object(trustcert, "LINUX_STORES", self.stores), \
                mock.patch.object(trustcert, "nss_db", return_value=self.tmp / "nssdb"), \
                mock.patch("sbxlib.trustcert.shutil.which", return_value="/usr/bin/certutil" if certutil else None):
            done = trustcert.install(runner, "sbx-dk", PEM, platform="linux")
        return done, runner.calls

    def test_system_store_and_browser_database(self):
        done, calls = self.run_install(certutil=True)
        self.assertEqual(len(done), 2)
        self.assertIn(["sudo", "update-ca-trust"], calls)
        self.assertTrue(any(c[:2] == ["sudo", "install"] and c[-1].endswith("sbx-dk.crt") for c in calls))
        add = [c for c in calls if c[0] == "certutil" and "-A" in c][0]
        self.assertEqual(add[add.index("-n") + 1], "sbx-dk")
        self.assertTrue(any("-N" in c for c in calls), "a missing database is created")

    def test_no_certutil_leaves_the_browser_alone(self):
        done, calls = self.run_install(certutil=False)
        self.assertEqual(len(done), 1)
        self.assertFalse([c for c in calls if c[0] == "certutil"])


LEAF = PEM.replace("abc123", "leaf")


class VerifyTest(unittest.TestCase):
    def test_openssl_decides(self):
        ok = Runner(responder=lambda a, d: Result(0))
        bad = Runner(responder=lambda a, d: Result(2))
        self.assertTrue(trustcert.verify(ok, PEM, LEAF))
        self.assertEqual(ok.calls[0][:3], ["openssl", "verify", "-CAfile"])
        self.assertFalse(trustcert.verify(bad, PEM, LEAF))


class CommandTest(unittest.TestCase):
    def import_ca(self, argv, *, verified=True, op=True, ssh=PEM):
        def respond(a, d):
            if a[0] == "ssh":
                return ssh if isinstance(ssh, Result) else ssh
            if a[:3] == ["op", "document", "get"]:
                return PEM
            if a[0] == "openssl":
                return Result(0 if verified else 2)
            return ""

        runner = Runner(responder=respond)
        api = FakeApi([], existing=["sbx-dk"])
        with mock.patch.object(trustcert, "install", return_value=["the system store"]) as install, \
                mock.patch("sbxlib.onepassword.available", return_value=op):
            code = cli.main(["import-ca", *argv], runner=runner, api=api)
        return code, install, runner.calls

    def test_the_ca_comes_from_1password_and_is_checked_against_the_sandbox(self):
        code, install, calls = self.import_ca(["--verify-with", "dk"])
        self.assertEqual(code, 0)
        self.assertIn(["op", "document", "get", "sbx mkcert CA"], calls)
        self.assertTrue(any(c[0] == "openssl" for c in calls))
        self.assertEqual(install.call_args.args[1:], ("sbx-mkcert-ca", PEM))

    def test_a_ca_that_did_not_sign_the_sandbox_is_refused(self):
        code, install, _ = self.import_ca(["--verify-with", "dk"], verified=False)
        self.assertEqual(code, 1)
        install.assert_not_called()

    def test_a_file_replaces_1password(self):
        with tempfile.NamedTemporaryFile("w", suffix=".pem") as f:
            f.write(PEM)
            f.flush()
            code, install, calls = self.import_ca(["--file", f.name], op=False)
        self.assertEqual(code, 0)
        self.assertFalse([c for c in calls if c[0] == "op"])
        install.assert_called_once()

    def test_without_the_flag_nothing_is_fetched_from_a_sandbox_or_verified(self):
        code, install, calls = self.import_ca([])
        self.assertEqual(code, 0)
        self.assertFalse([c for c in calls if c[0] in ("ssh", "openssl")])
        install.assert_called_once()

    def test_no_source_exits_1(self):
        code, install, _ = self.import_ca([], op=False)
        self.assertEqual(code, 1)
        install.assert_not_called()


class UploadTest(unittest.TestCase):
    def upload(self, *, existing=None):
        calls = []

        def respond(a, d):
            calls.append((a, d))
            if a[:3] == ["op", "document", "list"]:
                return '[{"title": "sbx mkcert CA"}]' if existing else "[]"
            if a[:3] == ["op", "document", "get"]:
                return existing
            return ""

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "rootCA.pem").write_text(PEM)
            with mock.patch("sbxlib.cli._mkcert_root", return_value=Path(d) / "rootCA.pem"), \
                    mock.patch("sbxlib.cli.shutil.which", return_value="/usr/bin/mkcert"), \
                    mock.patch("sbxlib.onepassword.available", return_value=True):
                code = cli.main(["import-ca", "--upload"], runner=Runner(responder=respond), api=FakeApi([]))
        return code, calls

    def test_stores_the_public_certificate_over_stdin(self):
        code, calls = self.upload()
        self.assertEqual(code, 0)
        create = [c for c in calls if c[0][:3] == ["op", "document", "create"]]
        self.assertEqual(len(create), 1)
        self.assertEqual(create[0][1], PEM.encode())
        self.assertNotIn("key", " ".join(create[0][0]).replace("--file-name", ""))

    def test_the_same_ca_is_left_alone(self):
        code, calls = self.upload(existing=PEM)
        self.assertEqual(code, 0)
        self.assertFalse([c for c in calls if c[0][:3] == ["op", "document", "create"]])

    def test_another_ca_is_never_replaced(self):
        code, calls = self.upload(existing=PEM.replace("abc123", "other"))
        self.assertEqual(code, 1)
        self.assertFalse([c for c in calls if c[0][:3] == ["op", "document", "create"]])


if __name__ == "__main__":
    unittest.main()
