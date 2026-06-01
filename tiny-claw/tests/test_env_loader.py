import os
import tempfile
import unittest

from internal.provider.env_loader import resolve_api_key


class EnvLoaderTests(unittest.TestCase):
    def test_resolve_api_key_reads_from_parent_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = os.path.join(temp_dir, "repo")
            work_dir = os.path.join(root_dir, "tiny-claw", "cmd")
            os.makedirs(work_dir)

            env_path = os.path.join(root_dir, ".env")
            with open(env_path, "w", encoding="utf-8") as env_file:
                env_file.write("ZHIPU_API_KEY=test-from-env-file\n")

            original = os.environ.pop("ZHIPU_API_KEY", None)
            try:
                api_key = resolve_api_key(start_dirs=[work_dir])
            finally:
                if original is not None:
                    os.environ["ZHIPU_API_KEY"] = original

        self.assertEqual("test-from-env-file", api_key)


if __name__ == "__main__":
    unittest.main()
