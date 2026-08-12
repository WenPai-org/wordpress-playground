import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('localization_overlay',ROOT/'tools/localization_overlay.py')
mod=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(mod)

class LocalizationOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=mod.load_catalog()
        cls.brand=json.loads((ROOT/'config/brand.json').read_text())
        cls.locale=json.loads((ROOT/'config/localization.json').read_text())

    def test_nonzero_catalog_coverage(self):
        self.assertGreaterEqual(mod.validate_catalog(self.catalog),40)
        self.assertGreaterEqual(len(self.catalog['entries']),40)

    def test_required_shell_surfaces_have_nonzero_samples(self):
        categories={entry['category'].split('-accessibility')[0] for entry in self.catalog['entries']}
        required={'dock-navigation','site-dialogs','errors-offline','loading-progress','save-storage-dialog','download-export','site-management','locale-bootstrap'}
        self.assertTrue(required.issubset(categories),required-categories)
        self.assertTrue(any('accessibility' in entry['category'] for entry in self.catalog['entries']))

    def test_placeholder_and_markup_tokens_are_preserved(self):
        for entry in self.catalog['entries']:
            self.assertEqual(mod.tokens(entry['old']),mod.tokens(entry['new']),entry['path'])

    def test_ui_and_wordpress_language_parameters_are_separate(self):
        self.assertEqual(self.locale['uiLanguageQueryParameter'],'ui-language')
        self.assertEqual(self.locale['wordpressLanguageQueryParameter'],'language')
        self.assertNotEqual(self.locale['uiLanguageQueryParameter'],self.locale['wordpressLanguageQueryParameter'])
        source=(ROOT/'overlays/files/packages/playground/website/src/lib/product-localization.ts').read_text()
        self.assertIn("UI_LANGUAGE_QUERY_PARAMETER = 'ui-language'",source)
        self.assertIn("WORDPRESS_LANGUAGE_QUERY_PARAMETER = 'language'",source)

    def test_default_languages_and_aliases(self):
        self.assertEqual(self.brand['defaultUiLanguage'],'zh_CN')
        self.assertEqual(self.brand['defaultWordPressLanguage'],'zh_CN')
        self.assertIn('zh-CN',self.locale['acceptedUiLanguageAliases'])
        self.assertIn('zh_CN',self.locale['acceptedUiLanguageAliases'])

    def test_brand_configuration_is_structured_and_preserves_attribution(self):
        self.assertEqual(self.brand['productName'],'文派 Playground')
        self.assertTrue(self.brand['productUrl'].startswith('https://'))
        self.assertEqual(self.brand['upstreamName'],'WordPress Playground')
        self.assertIn('WordPress Playground',self.brand['legalBrandAllowlist'])

    def test_overlay_paths_cannot_escape_source_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(mod.OverlayError): mod.safe_target(Path(tmp),'../escape')
            with self.assertRaises(mod.OverlayError): mod.safe_target(Path(tmp),'/absolute')

    def test_upstream_unit_contract_patch_preserves_coverage_and_asserts_chinese(self):
        patch=(ROOT/'overlays/patches/0001-localization-test-contract.patch').read_text()
        touched={line.removeprefix('+++ b/') for line in patch.splitlines() if line.startswith('+++ b/')}
        expected={
            'packages/playground/website/src/components/dock/dock-corner-launcher.spec.tsx',
            'packages/playground/website/src/components/dock/dock-pane.spec.tsx',
            'packages/playground/website/src/components/dock/dock-toggle-pill.spec.tsx',
            'packages/playground/website/src/components/site-manager/site-settings-form/site-settings-action-footer.spec.tsx',
        }
        self.assertEqual(touched,expected)
        added=[line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++')]
        removed=[line[1:] for line in patch.splitlines() if line.startswith('-') and not line.startswith('---')]
        self.assertEqual(len(added),18)
        self.assertEqual(len(removed),len(added))
        localized=('显示 Playground 工具','拖出或点击以显示 Playground 工具','关闭','显示工具',
                   '退出全宽','隐藏工具','全宽','当前无法隐藏工具','应用到此 Playground',
                   '更多设置操作','创建新的 Playground','丢弃当前工作并创建新的 Playground')
        for text in localized:
            self.assertTrue(any(text in line for line in added),text)
        # The patch only changes assertion operands and button lookup strings; it does not
        # remove test cases or behavior assertions to make the upstream suite green.
        self.assertFalse(any('it(' in line or 'test(' in line for line in removed))

    def test_locked_upstream_source_contract_when_provided(self):
        source=os.environ.get('PLAYGROUND_SOURCE_ROOT')
        if not source:
            self.skipTest('PLAYGROUND_SOURCE_ROOT not provided; exact-source gate runs in build CI')
        root=Path(source)
        for entry in self.catalog['entries']:
            target=mod.safe_target(root,entry['path'])
            self.assertTrue(target.is_file(),entry['path'])
            self.assertEqual(target.read_text().count(entry['old']),entry['expectedCount'],entry['path'])

if __name__=='__main__': unittest.main()
