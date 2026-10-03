"""Stage 4A release contract: source QCE compatibility must never ship."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PREFIX = "qq-napcat-candidate/"


def manifest():
    return json.loads((SCRIPTS / "windows_runtime_manifest.json").read_text(encoding="utf-8"))


def test_release_requires_complete_official_candidate_contract():
    candidate = json.loads((SCRIPTS / "qq_napcat_runtime_manifest.json").read_text())
    requirements = {entry['path'] for entry in manifest()['requirements']}
    assert {PREFIX + name for name in candidate['requiredFiles']} <= requirements
    assert {PREFIX + name for name in candidate['requiredDirectories']} <= requirements


def test_qce_is_not_a_release_asset():
    paths = [entry['path'] for key in ('requirements', 'packageDirectories') for entry in manifest()[key]]
    assert not any(path.startswith('qq/') or 'qce-server.exe' in path or 'napcat-plugin-qce' in path or 'static/qce' in path for path in paths)


def test_release_uses_official_napcat_pins_and_rejects_modified_artifacts():
    script = (SCRIPTS / 'build_windows_exe.ps1').read_text(encoding='utf-8-sig')
    assert 'qq_napcat_runtime_pins.json' in script
    assert 'patchedSha256' in script and 'Get-FileHash' in script
    assert 'pluginConfigSha256' in script and 'templates' in script
    assert 'qq_runtime_pins.json' not in script


def test_release_recursively_preserves_official_dependencies_only():
    directories = {entry['path'] for entry in manifest()['packageDirectories']}
    assert directories == {PREFIX + name for name in ('native', 'node_modules', 'worker', 'static')} | {'wechat/node_modules/koffi'}
    assert PREFIX + 'plugins' not in directories


def test_release_declares_private_and_generated_candidate_state():
    private = {entry['path'] for entry in manifest()['privatePaths']}
    assert {PREFIX + name for name in ('cache', 'logs', 'config/plugins', 'loadNapCat.js', 'qqnt.echo.json')} <= private




def test_release_bootstrap_uses_only_official_napcat_contract():
    assert manifest()["qqPins"] == "qq_napcat_runtime_pins.json"
