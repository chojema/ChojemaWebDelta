"""빌드 환경의 실제 의존성에서 배포용 라이선스 고지를 모은다."""

import argparse
from importlib import metadata
from pathlib import Path
import sys

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent


def runtime_packages() -> list[str]:
    pending = ["httpx", "beautifulsoup4"]
    found: set[str] = set()
    while pending:
        name = pending.pop().lower().replace("_", "-")
        if name in found:
            continue
        distribution = metadata.distribution(name)
        found.add(name)
        for value in distribution.requires or []:
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return sorted(found)


def write_notices(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "LICENSE.txt").write_text((ROOT / "LICENSE").read_text(), encoding="utf-8")
    sections = [
        "ChojemaWebDelta — Third-party notices\n\n"
        "The original ChojemaWebDelta code, including version 0.1.0, is licensed\n"
        "under the MIT License in LICENSE.txt. The components below retain their\n"
        "own licenses; the application license does not replace those licenses.\n\n"
        "CPython is bundled without changes to its source. Packaging relocates\n"
        "the runtime and loads the application from PyInstaller archives.\n"
        f"Runtime series: CPython {sys.version_info.major}.{sys.version_info.minor}.\n\n"
        "OpenSSL, libffi, Zstandard and other components described in the Python\n"
        "notices may be included according to platform. Windows builds also\n"
        "include Microsoft runtime components supplied with CPython; their\n"
        "terms are reproduced in the Microsoft-runtime section below.\n"
    ]
    for name in [*runtime_packages(), "pyinstaller"]:
        distribution = metadata.distribution(name)
        license_files = [
            file for file in distribution.files or []
            if file.name.lower().startswith(("license", "licence", "copying", "notice"))
        ]
        if not license_files:
            raise RuntimeError(f"{name}: 배포할 라이선스 파일을 찾을 수 없습니다.")
        header = (
            f"{distribution.metadata['Name']} {distribution.version}\n"
            f"Upstream source: https://pypi.org/project/{distribution.metadata['Name']}/{distribution.version}/#files\n"
            "Bundled from the upstream distribution without source changes."
        )
        sections.append("\n" + "=" * 78 + "\n" + header + "\n" + "=" * 78 + "\n")
        for file in sorted(license_files, key=str):
            sections.append(distribution.locate_file(file).read_text(encoding="utf-8"))
    for file in sorted((ROOT / "packaging" / "licenses").glob("*.txt")):
        sections.append("\n" + "=" * 78 + "\n" + file.stem + "\n" + "=" * 78 + "\n")
        sections.append(file.read_text(encoding="utf-8"))
    notices = destination / "THIRD_PARTY_NOTICES.txt"
    notices.write_text("\n".join(sections), encoding="utf-8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_notices(args.output)
