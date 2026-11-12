import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('repair_metadata', ROOT/'docker/repair_cusparselt_metadata.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class MetadataRepairTests(unittest.TestCase):
    def fixture(self, root, machine=183, tag='sbsa'):
        wheel=Path('nvidia_cusparselt_cu13-0.8.1.dist-info/WHEEL')
        record=wheel.with_name('RECORD')
        library=Path('nvidia/cusparselt/lib/libcusparseLt.so.0')
        for path in (wheel,library):(root/path).parent.mkdir(parents=True,exist_ok=True)
        (root/wheel).write_text(f'Wheel-Version: 1.0\nTag: py3-none-manylinux2014_{tag}\n')
        header=bytearray(64);header[:6]=b'\x7fELF\x02\x01';struct.pack_into('<H',header,18,machine)
        (root/library).write_bytes(header)
        rows=[]
        for path in (wheel,library):
            data=(root/path).read_bytes()
            rows.append([str(path),module.encoded_hash(hashlib.sha256(data).digest()),str(len(data))])
        out=io.StringIO();csv.writer(out).writerows(rows);(root/record).write_text(out.getvalue())
        dist=SimpleNamespace(version='0.8.1',files=[wheel,record,library],locate_file=lambda p:root/p)
        return dist,wheel,record,library

    def test_repairs_only_metadata_and_updates_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dist,wheel,record,library=self.fixture(root)
            before=(root/library).read_bytes()
            self.assertTrue(module.repair(dist,root/'audit.json',machine='aarch64',system='Linux'))
            self.assertIn('aarch64',(root/wheel).read_text())
            self.assertEqual((root/library).read_bytes(),before)
            rows={row[0]:row for row in csv.reader(io.StringIO((root/record).read_text()))}
            self.assertEqual(rows[str(wheel)][1],module.encoded_hash(hashlib.sha256((root/wheel).read_bytes()).digest()))
            self.assertFalse(module.repair(dist,root/'audit.json',machine='aarch64',system='Linux'))

    def test_refuses_x86_binary_and_leaves_metadata_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dist,wheel,record,_=self.fixture(root,machine=62)
            before=((root/wheel).read_bytes(),(root/record).read_bytes())
            with self.assertRaisesRegex(ValueError,'AArch64'):
                module.repair(dist,root/'audit.json',machine='aarch64',system='Linux')
            self.assertEqual(((root/wheel).read_bytes(),(root/record).read_bytes()),before)

    def test_refuses_corrupt_native_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dist,wheel,_,library=self.fixture(root)
            (root/library).write_bytes((root/library).read_bytes()+b'corruption')
            with self.assertRaisesRegex(ValueError,'checksum'):
                module.repair(dist,root/'audit.json',machine='aarch64',system='Linux')
            self.assertIn('sbsa',(root/wheel).read_text())
