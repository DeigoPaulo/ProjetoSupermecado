from pathlib import Path
import unittest


class InstallerTemplateTests(unittest.TestCase):
    def test_shortcuts_are_conventional_and_define_the_brand_icon(self):
        template = (Path(__file__).parent / "installer" / "Product.wxs.template").read_text(encoding="utf-8")
        self.assertIn('Icon="DeigoPdvIcon"', template)
        self.assertNotIn('Advertise="yes"', template)
        self.assertEqual(template.count('Advertise="no"'), 2)


if __name__ == "__main__":
    unittest.main()
