import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import bootstrap


class BootstrapTests(unittest.TestCase):
    def test_video_models_require_explicit_opt_in(self):
        for flag in [[],['--with-video']]:
            with self.subTest(arguments=flag), tempfile.TemporaryDirectory() as directory:
                with patch.object(bootstrap,'ROOT',Path(directory)), patch.object(bootstrap,'SOURCES',[]), patch('sys.argv',['bootstrap.py',*flag]), patch.dict(os.environ), patch('subprocess.run') as external, patch('builtins.print'):
                    bootstrap.main()
                commands=[list(map(str,call.args[0])) for call in external.call_args_list]
                scripts=[arg for command in commands for arg in command if arg.startswith('scripts/download_')]
                self.assertIn('scripts/download_models.py',scripts)
                self.assertEqual('scripts/download_video_models.py' in scripts,bool(flag))
                self.assertEqual('scripts/download_creative_models.py' in scripts,bool(flag))


if __name__=='__main__':unittest.main()
