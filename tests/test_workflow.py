import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('generate', ROOT / 'scripts/generate_video.py')
generate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate)


class WorkflowTests(unittest.TestCase):
    def test_image_input_and_parameters_are_connected(self):
        wf = generate.build_workflow('prompt', 'test', 736, 416, 124, 123, 'reference.png')
        self.assertEqual(wf['7']['inputs']['first_frame'], ['15', 0])
        self.assertEqual(wf['15']['inputs']['image'], 'reference.png')
        self.assertEqual(wf['7']['inputs']['length'], 124)
        self.assertEqual(wf['9']['inputs']['seed'], 123)
        for node in wf.values():
            for value in node['inputs'].values():
                if isinstance(value, list):
                    self.assertIn(value[0], wf)
        self.assertEqual(wf['14']['inputs']['filename_prefix'], 'audio/test')

    def test_reads_actual_history_filename(self):
        outputs = {'13': {'images': [{'filename': 'actual_00037_.mp4', 'subfolder': 'video', 'type': 'output'}]}}
        self.assertEqual(generate.output_path(outputs, '13', ('.mp4',)),
                         '/opt/ComfyUI/output/video/actual_00037_.mp4')

    def test_rejects_missing_audio_and_unsafe_paths(self):
        with self.assertRaises(RuntimeError):
            generate.output_path({}, '14', ('.flac',))
        for filename, subfolder in [('../bad.mp4', ''), ('/bad.mp4', ''), ('ok.mp4', '/tmp')]:
            with self.subTest(filename=filename, subfolder=subfolder), self.assertRaises(ValueError):
                generate.output_path({'13': {'images': [{'filename': filename, 'subfolder': subfolder, 'type': 'output'}]}}, '13', ('.mp4',))

    def test_generation_error_is_not_treated_as_completion(self):
        record = {'task': {'status': {'completed': False, 'status_str': 'error'}}}
        with patch.object(generate, 'api', return_value=record), self.assertRaisesRegex(RuntimeError, 'Generation failed'):
            generate.wait_for_prompt('http://example', 'task', 10, 1)

    def test_mux_maps_both_tracks_and_rejects_silent_result(self):
        probe = subprocess.CompletedProcess([], 0, stdout=json.dumps({'streams': [{'codec_type': 'video'}], 'format': {'duration': '4'}}))
        with patch.object(generate.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 0), probe]) as run:
            with self.assertRaisesRegex(RuntimeError, 'video, audio'):
                generate.mux_and_validate('container', '/video.mp4', '/audio.flac', 'test')
            args = run.call_args_list[0].args[0]
            self.assertIn('0:v:0', args)
            self.assertIn('1:a:0', args)
            self.assertIn('loudnorm=I=-16:TP=-1.5:LRA=11', args)

    def test_dry_run_works_without_service(self):
        result = subprocess.run(['python3', str(ROOT / 'scripts/generate_video.py'), '--print-workflow'], check=True, capture_output=True, text=True)
        self.assertIn('14', json.loads(result.stdout))


class SourceTests(unittest.TestCase):
    def test_mismatched_source_fails_before_downloading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            for name in ('common.sh', 'prepare_comfyui_src.sh'):
                (root / 'scripts' / name).write_text((ROOT / 'scripts' / name).read_text())
            (root / '.env').write_text('COMFYUI_REF=v0.30.0\n')
            (root / 'comfyui-src/comfy').mkdir(parents=True)
            marker = root / 'comfyui-src/.h3-source-ref'
            marker.write_text('v0.29.0\n')
            result = subprocess.run(['bash', str(root / 'scripts/prepare_comfyui_src.sh')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('another ref', result.stderr)
            self.assertEqual(marker.read_text(), 'v0.29.0\n')
            marker.write_text('v0.30.0\n')
            result = subprocess.run(['bash', str(root / 'scripts/prepare_comfyui_src.sh')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
