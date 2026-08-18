"""Build a fail-closed macOS Seatbelt (sandbox-exec) profile.

The profile uses version 1 (deny default) syntax — the form Chromium itself
uses in production. Apple has never published a complete SBPL specification;
``sandbox-exec`` and ``sandbox_init`` are deprecated but remain functional on
current macOS. We do NOT claim a version 3 profile because its semantics and
portability cannot be verified against any public spec (U4-SANDBOX-REAL
research, 2026-08-06).

The profile denies everything by default and re-allows only the narrow set of
operations the staged game/mod actually needs: reading system libraries,
writing to explicitly-granted temporary directories, and (optionally) limited
process execution. Network is always denied.
"""

from __future__ import annotations


def build_seatbelt_profile(
    writable_dirs: list[str],
    *,
    allow_network: bool = False,
    allow_process_exec: bool = True,
) -> str:
    """Build a version-1 fail-closed Seatbelt profile string.

    Args:
        writable_dirs: Absolute paths the sandboxed process may write to.
            These should be temporary staging directories only.
        allow_network: If False (the default and recommended setting), all
            network access is denied.
        allow_process_exec: If True, allow executing signed system binaries.
            A headless game launch needs this; pure script validation may not.

    Returns:
        A Seatbelt profile string suitable for ``sandbox-exec -p``.

    Notes:
        - Always run the sandboxed process with ``close_fds=True``: Seatbelt
          checks happen at resource-acquisition time, so file descriptors
          already open before the sandbox engages remain usable.
        - ``sandbox-exec`` is deprecated; this is a defense-in-depth layer, not
          a guarantee against kernel-level or memory-corruption escapes.
    """
    lines: list[str] = ["(version 1)", "(deny default)"]
    # Read access to system libraries and frameworks (needed to launch any binary).
    lines.append('(allow file-read* (subpath "/usr"))')
    lines.append('(allow file-read* (subpath "/System/Library"))')
    lines.append('(allow file-read* (subpath "/Library"))')
    # Explicitly granted write directories.
    for d in writable_dirs:
        escaped = d.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'(allow file-write* (subpath "{escaped}"))')
    # Process execution (needed for headless game launch).
    if allow_process_exec:
        lines.append('(allow process-exec (subpath "/usr/bin"))')
        lines.append('(allow process-exec (subpath "/bin"))')
    # Network — fail-closed by default.
    if not allow_network:
        lines.append("(deny network)")
    else:  # pragma: no cover - opt-in only, discouraged
        lines.append("(allow network)")
    return "\n".join(lines) + "\n"


def profile_for_temp_staging(staging_dir: str, *, allow_network: bool = False) -> str:
    """Convenience: build a profile granting write only to one staging dir."""
    return build_seatbelt_profile([staging_dir], allow_network=allow_network)
