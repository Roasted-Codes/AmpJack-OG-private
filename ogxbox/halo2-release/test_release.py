#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable package checks; strict CPU tests require AMPJACK_TEST_XBE."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build
        cls.b = build
        cls.tmp = tempfile.TemporaryDirectory(prefix='ampjack-', dir=os.environ.get('TMPDIR'))
        cls.out = Path(cls.tmp.name) / 'output'
        subprocess.run([sys.executable, str(ROOT/'build.py'), '--out', str(cls.out)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_package_identity_and_metadata(self):
        data, man = self.b.check(self.out)
        self.assertEqual(man['payload_sha256'], '8bf54869e1635fbcb8313226da7abd243c0b4fc4729b1b664f2828e030380448')
        self.assertEqual(man['resident_alloc'], 45056)
        self.assertEqual(man['file_buffer_alloc'], 24576)
        self.assertEqual(man['image_size'], 20492)
        self.assertEqual(man['mem_end'], 43912)
        self.assertEqual(man['module_entry_flags'], 0)
        self.assertIn(self.b.NATIVE_PATH.encode()+b'\0', data)
        self.assertNotIn(b'AmpJack63-u803', data)

    def test_reproducible(self):
        other = Path(self.tmp.name)/'repeat'
        self.b.build(other)
        for rel in ('manifest.json', 'SHA256SUMS', self.b.ZIP_NAME, 'candidate/'+self.b.NAMES[0], 'candidate/'+self.b.NAMES[1]):
            self.assertEqual((self.out/rel).read_bytes(), (other/rel).read_bytes(), rel)

    def test_sources_and_payload_rejections(self):
        self.b.verify_inputs()
        m = self.b.module()
        p = self.b.package(m)
        for bad in (p[:-1], p+b'\0', p[:64]+b'\0'+p[65:]):
            with self.assertRaises(ValueError): self.b.check_payload(bad, m)
        m.relocs.append(m.relocs[0])
        with self.assertRaises(AssertionError): self.b.package(m)

    def test_archive_inventory_and_sums(self):
        import zipfile, hashlib
        with zipfile.ZipFile(self.out/self.b.ZIP_NAME) as z:
            self.assertEqual(sorted(z.namelist()), sorted(['candidate/'+n for n in self.b.NAMES]+['README.md','COPYING.GPL-3','NOTICES.txt','manifest.json']))
            for name in z.namelist():
                self.assertEqual(z.read(name), (self.out/name).read_bytes())
        for line in (self.out/'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ')
            self.assertEqual(hashlib.sha256((self.out/name).read_bytes()).hexdigest(), digest)

# The original real-wrapper suite is loaded only with explicitly supplied game.
# No replacement/fabricated title data is used when the XBE is absent.
def load_tests(loader, tests, pattern):
    suite = loader.loadTestsFromTestCase(PackageTests)
    if os.environ.get('AMPJACK_TEST_XBE'):
        import wrapper_harness as h
        import build
        h.OUT = Path(os.environ.get('AMPJACK_TEST_OUT', ROOT/'dist'))
        build.build(h.OUT)
        suite.addTests(loader.loadTestsFromTestCase(h.Tests))
    else:
        print('Strict actual-wrapper CPU tests NOT RUN: set AMPJACK_TEST_XBE to owner-supplied pinned XBE.')
    return suite

if __name__ == '__main__':
    unittest.main(verbosity=2)
