"""QQ program, work and snapshot directory contract.

Path calculation is pure; the shared resolver validates release metadata and
optionally prepares the work copy. Startup requires explicit managed/custom
provenance; untagged saved configurations remain untouched for manual review.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from ...resources import default_qq_runtime_directory, user_data_root
from .qq_environment_config import QQEnvironmentConfig


class AmbiguousQQRuntime(ValueError):
    """An old saved path does not prove managed or custom ownership."""

    code = "qq_runtime_ownership_unknown"
    public_message = "旧 QQ 运行配置的归属无法确认，请明确选择当前内置组件或自定义目录。"


@dataclass(frozen=True, slots=True)
class QQRuntimePaths:
    program_root: Path
    work_root: Path
    snapshot_root: Path

    @property
    def runtime_id(self) -> str:
        """Opaque binding for Echo's own bridge, never an upstream setting."""
        values = (self.program_root, self.work_root, self.snapshot_root)
        body = "\n".join(p.resolve().as_uri() for p in values)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


def resolve_runtime_paths(config: QQEnvironmentConfig, *, prepare=False) -> QQRuntimePaths:
    """One path policy for startup, QR and snapshot consumers."""
    if config.runtime_mode == "custom":
        if config.runtime_directory is None:
            raise ValueError("Custom QQ runtime requires an explicit path")
        program = config.runtime_directory.resolve()
        return QQRuntimePaths(program, program, program.parent / "output/qq_direct_db_phase35")
    if config.runtime_mode != "managed":
        raise AmbiguousQQRuntime(AmbiguousQQRuntime.public_message)
    from .qq_environment_config import default_qq_runtime_directory
    from ... import resources
    from .qq_runtime_workspace import _components, prepare_qq_workspace
    program = default_qq_runtime_directory().resolve()
    manifest = resources.resource_path("scripts/windows_runtime_manifest.json")
    if prepare:
        return prepare_qq_workspace(program, manifest)
    component, _ = _components(program, manifest)
    return qq_runtime_paths(component_id=component, program_root=program)


def qq_runtime_paths(
    config: QQEnvironmentConfig | None = None,
    *,
    component_id: str,
    program_root: Path | None = None,
    data_root: Path | None = None,
) -> QQRuntimePaths:
    """Compute paths; managed installs follow today's bundle, custom paths stay.

    The component id is the content/contract digest produced by preparation,
    rather than an install location or an application version.
    """
    if re.fullmatch(r"[0-9a-f]{64}", component_id) is None:
        raise ValueError("Invalid QQ component identity")
    program = Path(program_root) if program_root is not None else default_qq_runtime_directory()
    if config is not None:
        if config.runtime_mode == "custom":
            if config.runtime_directory is None:
                raise ValueError("Custom QQ runtime requires an explicit path")
            program = config.runtime_directory
        elif config.runtime_mode != "managed":
            if config.runtime_mode is not None or config.runtime_directory is not None:
                raise AmbiguousQQRuntime("QQ runtime ownership requires an explicit choice")
    user = Path(data_root) if data_root is not None else user_data_root()
    return QQRuntimePaths(
        program_root=program,
        work_root=user / "runtime" / "qq" / component_id,
        snapshot_root=user / "transient" / "qq-direct-db",
    )
