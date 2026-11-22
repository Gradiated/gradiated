"""Offline runtime, environment pins and actual macOS boundary checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import runtime


class RuntimeContract(unittest.TestCase):
    def test_environment_drops_credentials_and_startup_injection(self):
        original={'HOME':'/synthetic','PATH':'/usr/bin','HF_TOKEN':'synthetic','AWS_SECRET_ACCESS_KEY':'synthetic',
                  'PYTHONPATH':'/injection','BASH_ENV':'/injection','SSLKEYLOGFILE':'/injection','MLX_ENABLE_TF32':'1'}
        result=runtime.clean_environment(Path('/runtime'),original)
        self.assertEqual(result['MLX_ENABLE_TF32'],'0')
        for key in ('HF_TOKEN','AWS_SECRET_ACCESS_KEY','PYTHONPATH','BASH_ENV','SSLKEYLOGFILE'):
            self.assertNotIn(key,result)

    def test_every_worker_is_offline_and_write_restricted(self):
        for stage in ('chat','verify','train','fixed','fixed-smoke','rtl','rtl-rope','rtl-cache','conditioned-prepare','conditioned-train','conditioned-eval','conditioned-chat','conditioned-probe','conditioned-convert','conditioned-check'):
            command=runtime.launch_arguments([stage])
            profile=command[command.index('-p')+1]
            self.assertIn('(deny network*)',profile)
            self.assertIn('(deny file-write*)',profile)
            self.assertNotIn('models/tiny',profile)
            self.assertIn('-I',command)
            self.assertIn('-B',command)

    def test_unpinned_or_missing_environment_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            names={'mlx':'0.32.4','mlx-lm':'0.32.2','numpy':'2.5.4','transformers':'5.22.1'}
            (root/'uv.lock').write_text('\n'.join(f'[[package]]\nname="{n}"\nversion="{v}"\nsource={{registry="https://pypi.org/simple"}}' for n,v in names.items()))
            with self.assertRaises(ValueError):runtime.verify_environment(root,root)
            for name,version in names.items():
                info=root/'venv/lib/python3.12/site-packages'/(name+'.dist-info');info.mkdir(parents=True)
                (info/'METADATA').write_text(f'Name: {name}\nVersion: {version}\n')
            runtime.verify_environment(root,root)
            (info/'METADATA').write_text('Name: transformers\nVersion: 0.0.0\n')
            with self.assertRaises(ValueError):runtime.verify_environment(root,root)

    @unittest.skipUnless(sys.platform=='darwin','macOS sandbox-exec required')
    def test_live_network_and_protected_write_denial(self):
        probe=r'''
import socket,uuid,json
from pathlib import Path
project=Path(PROJECT_VALUE);runtime=Path(RUNTIME_VALUE)
try:socket.create_connection(('127.0.0.1',9),timeout=2)
except PermissionError:pass
else:raise RuntimeError('Network permitted')
for directory in (project/'tools',runtime/'venv',runtime/'models/tiny',Path('/private/tmp')):
 target=directory/('.tiny-security-'+uuid.uuid4().hex)
 try:target.write_text('synthetic probe')
 except PermissionError:pass
 else:
  target.unlink();raise RuntimeError('Protected path writable')
target=runtime/'outputs'/('.tiny-security-'+uuid.uuid4().hex)
target.write_text('synthetic probe');target.unlink()
print(json.dumps({'network_denied':True,'protected_writes_denied':True,'output_write_allowed':True}))
'''.replace('PROJECT_VALUE',repr(str(runtime.PROJECT))).replace('RUNTIME_VALUE',repr(str(runtime.RUNTIME)))
        command=runtime.launch_arguments(['verify']);i=command.index(str(runtime.PROJECT/'tools/generative.py'))
        command=command[:i]+['-c',probe]
        result=subprocess.run(command,capture_output=True,text=True,timeout=30,check=True,
                              env=runtime.clean_environment(runtime.RUNTIME,{}))
        self.assertTrue(json.loads(result.stdout)['protected_writes_denied'])

    def test_launcher_ignores_shell_and_python_startup_injection(self):
        with tempfile.TemporaryDirectory(dir=runtime.RUNTIME/'tmp') as directory:
            folder=Path(directory);marker=folder/'python-marker';shell_marker=folder/'shell-marker'
            (folder/'sitecustomize.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').touch()\n')
            shell=folder/'bash_env.sh';shell.write_text('touch "'+str(shell_marker)+'"\n')
            result=subprocess.run([str(runtime.PROJECT/'generative.sh'),'--help'],capture_output=True,text=True,
                                  timeout=30,check=True,env=dict(os.environ,PYTHONPATH=str(folder),BASH_ENV=str(shell)))
            self.assertIn('usage:',result.stdout)
            self.assertFalse(marker.exists());self.assertFalse(shell_marker.exists())



class DesktopConfigContract(unittest.TestCase):
    """The embedded Linux config editor must fail closed before services start."""

    def run_config(self, xrdp_text, sesman_text, symlink=False):
        source = (runtime.PROJECT / "desktop-setup.sh").read_text()
        editor = source.split("<<'DESKTOP_CONFIG'\n", 1)[1].split("\nDESKTOP_CONFIG\n", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "xrdp.ini"
            real = root / "original.ini"
            if symlink:
                real.write_text(xrdp_text)
                target.symlink_to(real)
            else:
                target.write_text(xrdp_text)
            session = root / "sesman.ini"
            session.write_text(sesman_text)
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", editor, str(target), str(session)],
                capture_output=True, text=True, timeout=10,
            )
            return result, target.read_text(), session.read_text()

    def test_desktop_is_local_tls_only_without_root_or_drive_access(self):
        import configparser
        xrdp = "[Globals]\nport=3389\nsecurity_layer=negotiate\npercent=100%\n[Channels]\nrdpdr=true\n[Xorg]\nport=-1\nparam=first\nparam=second\n"
        session = "[Globals]\nListenAddress=0.0.0.0\n[Security]\nAllowRootLogin=true\n[Sessions]\nIdleTimeLimit=0\n"
        result, output, session_output = self.run_config(xrdp, session)
        self.assertEqual(result.returncode, 0, result.stderr)
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config.read_string(output)
        self.assertEqual(config["Globals"]["port"], "tcp://127.0.0.1:3389")
        self.assertEqual(config["Globals"]["security_layer"], "tls")
        self.assertEqual(config["Globals"]["ssl_protocols"], "TLSv1.2,TLSv1.3")
        self.assertEqual(config["Globals"]["percent"], "100%")
        self.assertEqual(config["Xorg"]["port"], "-1")
        self.assertIn("param=first\nparam=second\n", output)
        self.assertEqual(config["Channels"]["rdpdr"], "false")
        config.read_string(session_output)
        self.assertEqual(config["Globals"]["ListenAddress"], "127.0.0.1")
        self.assertEqual(config["Security"]["AllowRootLogin"], "false")
        self.assertEqual(config["Sessions"]["IdleTimeLimit"], "900")
        self.assertEqual(config["Sessions"]["KillDisconnected"], "false")

    def test_ambiguous_or_missing_config_sections_are_rejected(self):
        for text in ("[Globals]\nport=1\nport=2\n[Channels]\n", "[WrongSection]\nport=3389\n", "[Globals]\nport=3389\n[Globals]\n[Channels]\n"):
            with self.subTest(config=text):
                result, output, _ = self.run_config(text, "[Globals]\n[Security]\n[Sessions]\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, text)

    def test_symlinked_desktop_config_is_rejected(self):
        text = "[Globals]\nport=3389\n[Channels]\n"
        result, output, _ = self.run_config(text, "[Globals]\n[Security]\n[Sessions]\n", symlink=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, text)


class DesktopListenerContract(unittest.TestCase):
    """Check real ss address forms without starting services or making connections."""

    def setUp(self):
        source = (runtime.PROJECT / "desktop-setup.sh").read_text()
        checker = source.split("<<'DESKTOP_LISTENERS'\n", 1)[1].split("\nDESKTOP_LISTENERS\n", 1)[0]
        namespace = {"__name__": "listener_test"}
        exec(compile(checker, "desktop-listener-check", "exec"), namespace)
        self.validate = namespace["validate_listeners"]

    @staticmethod
    def listeners(*addresses):
        return "".join(f"LISTEN 0 128 {address} *:*\n" for address in addresses)

    def test_ipv4_ipv6_and_dual_loopback_session_manager(self):
        for addresses in (("127.0.0.1:3350",), ("[::1]:3350",),
                          ("127.0.0.1:3350", "[::1]:3350")):
            with self.subTest(session_manager=addresses):
                result = self.validate(self.listeners("127.0.0.1:3389", *addresses,
                                                     "0.0.0.0:22", "[::]:22"))
                self.assertEqual(result[3389], ["127.0.0.1:3389"])
                self.assertEqual(result[3350], list(addresses))

    def test_exposed_or_unexpected_listeners_are_rejected_even_with_safe_listener(self):
        for port in (3389, 3350):
            for host in ("0.0.0.0", "[::]", "*", "62.83.44.95", "100.73.61.0",
                         "[fd7a:115c:a1e0::1]", "[::ffff:62.83.44.95]"):
                with self.subTest(port=port, host=host):
                    with self.assertRaises(SystemExit):
                        self.validate(self.listeners("127.0.0.1:3389", "[::1]:3350",
                                                     f"{host}:{port}"))
        with self.assertRaises(SystemExit):
            self.validate(self.listeners("[::1]:3389", "[::1]:3350"))

    def test_missing_listeners_are_distinct_from_unsafe_or_malformed_output(self):
        self.assertEqual(self.validate(""), {3389: [], 3350: []})
        self.assertEqual(self.validate(self.listeners("127.0.0.1:3389")),
                         {3389: ["127.0.0.1:3389"], 3350: []})
        with self.assertRaises(SystemExit):
            self.validate("unexpected output")


if __name__=='__main__':unittest.main()
