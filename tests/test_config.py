import unittest
import tempfile
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

    def test_installed_package_does_not_load_dotenv_from_working_directory(self):
        with patch.object(config, "RUNNING_FROM_SOURCE", False), \
             patch.object(config, "CONFIG_FILE", config.Path("/tmp/kubebot-config/.env")):
            self.assertEqual(list(config._dotenv_paths()), [config.Path("/tmp/kubebot-config/.env")])

    def test_source_checkout_loads_development_dotenv(self):
        with patch.object(config, "RUNNING_FROM_SOURCE", True), \
             patch.object(config, "CONFIG_FILE", config.Path("/tmp/kubebot-config/.env")), \
             patch.object(config, "PROJECT_ROOT", config.Path("/src/kubebot")), \
             patch.object(config.Path, "cwd", return_value=config.Path("/work")):
            self.assertEqual(
                list(config._dotenv_paths()),
                [
                    config.Path("/tmp/kubebot-config/.env"),
                    config.Path("/work/.env"),
                    config.Path("/src/kubebot/.env"),
                ],
            )

    def test_ollama_interactive_configuration_is_saved(self):
        with patch.object(config, "LLM_PROVIDER", ""), \
             patch.object(config.sys.stdin, "isatty", return_value=True), \
             patch.object(config.Prompt, "ask", return_value="ollama"), \
             patch.object(config, "_save_settings") as save_settings:
            config.configure_provider(force_prompt=True)

        save_settings.assert_called_once()
        self.assertIn("KUBEBOT_LLM_PROVIDER=ollama", save_settings.call_args.args[0])

    def test_saved_configuration_is_private_and_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            config_file = config.Path(directory) / ".env"
            with patch.object(config, "CONFIG_DIR", config_file.parent), \
                 patch.object(config, "CONFIG_FILE", config_file):
                config._save_settings(["KUBEBOT_LLM_PROVIDER=ollama"])

            self.assertEqual(config_file.read_text(encoding="utf-8"), "KUBEBOT_LLM_PROVIDER=ollama\n")
            if config.os.name != "nt":
                self.assertEqual(config_file.parent.stat().st_mode & 0o777, 0o700)
                self.assertEqual(config_file.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()