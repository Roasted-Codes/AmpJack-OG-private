"""Regression: minute checks must not post the same update again."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('progress', Path(__file__).with_name('progress_5m.py'))
assert spec is not None and spec.loader is not None
progress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(progress)


class ProgressReportingTest(unittest.TestCase):
    def test_changes_only(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            receipt = Path(directory) / 'last.txt'
            data = {'owner_verified_result': 'Test result A.', 'owner_next_check': 'Test action B.'}

            def run():
                state.write_text(json.dumps(data))
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    progress.main(state, receipt)
                return output.getvalue()

            self.assertEqual(run(), 'Test result A. Test action B.\n')
            self.assertEqual(run(), '')
            data['updated'] = 'metadata-only change'
            self.assertEqual(run(), '')
            data['owner_verified_result'] = 'Test result C.'
            self.assertEqual(run(), 'Test result C. Test action B.\n')
            self.assertEqual(run(), '')
            data['owner_required_action'] = 'Test approval needed.'
            self.assertIn('Test approval needed.', run())
            self.assertEqual(run(), '')


if __name__ == '__main__':
    unittest.main()
