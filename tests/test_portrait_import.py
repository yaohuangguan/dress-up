import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from scripts import import_portraits


class PortraitImportTests(unittest.TestCase):
    def test_invalid_ids_cannot_escape_preview_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            cache=Path(directory)
            for key in ['../outside','f0000000000/../../private','f0000000000;cmd','']:
                with self.subTest(identifier=key), self.assertRaisesRegex(ValueError,'Invalid source'):
                    import_portraits.copy_preview({'id':key},cache)
            self.assertEqual(list(cache.iterdir()),[])

    def test_disguised_png_is_rejected_before_publishing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(import_portraits,'ROOT',Path(directory)):
            cache=Path(directory)/'cache';cache.mkdir()
            Image.new('RGB',(12,16)).save(cache/'f0123456789.webp',format='PNG')
            with self.assertRaisesRegex(ValueError,'Unexpected preview'):
                import_portraits.copy_preview({'id':'f0123456789'},cache)
            self.assertFalse((Path(directory)/'data').exists())

    def test_verified_webp_is_published_under_local_library(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(import_portraits,'ROOT',Path(directory)):
            root=Path(directory);cache=root/'cache';cache.mkdir()
            target=root/'data/library/portraits';target.mkdir(parents=True)
            source=cache/'f0123456789.webp'
            Image.new('RGB',(12,16)).save(source,format='WEBP')
            import_portraits.copy_preview({'id':'f0123456789'},cache)
            self.assertEqual((target/source.name).read_bytes(),source.read_bytes())
            self.assertEqual(list(target.glob('*.partial')),[])


if __name__=='__main__':unittest.main()
