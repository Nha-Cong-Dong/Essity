"""The runtime image installs no dev group: nothing under src may import a dev-only stub."""

import subprocess
import sys

BLOCKED = ("mypy_boto3_s3", "mypy_boto3_builder", "types_boto3", "boto3_stubs", "botocore_stubs")


def test_main_imports_without_dev_only_stubs() -> None:
    code = (
        "import sys\n"
        f"for name in {BLOCKED!r}:\n"
        "    sys.modules[name] = None\n"
        "import core_api.main\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
