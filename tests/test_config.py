import unittest
from unittest.mock import patch

from kubebot import cli, config


class ProviderConfigurationTests(unittest.TestCase):
    def test_version_flag_exits_before_provider_setup(self):
        with patch("sys.argv", ["kubebot", "--version"]), self.assertRaises(SystemExit) as result:
            cli.main()

        self.assertEqual(result.exception.code, 0)

    def test_explicit_ollama_provider_needs_no_azure_credentials(self):
        with patch.object(config, "LLM_PROVIDER", "ollama"), \
             patch.object(config, "AZURE_OPENAI_ENDPOINT", None), \
             patch.object(config, "AZURE_OPENAI_API_KEY", None):
            config.configure_provider()

            self.assertEqual(config.LLM_PROVIDER, "ollama")

    def test_invalid_provider_is_rejected(self):
        with patch.object(config, "LLM_PROVIDER", "invalid"):
            with self.assertRaisesRegex(RuntimeError, "azure.*ollama"):
                config.configure_provider()

    def test_document_paths_do_not_depend_on_working_directory(self):
        self.assertTrue(all(path.is_absolute() for path in config.DOC_PATHS))
        self.assertTrue(all(path.exists() for path in config.DOC_PATHS))

    def test_vector_store_uses_user_data_directory(self):
        self.assertNotEqual(config.PERSIST_DIR.parent.parent, config.PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()