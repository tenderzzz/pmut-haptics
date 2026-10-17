"""Package the built source archive and standalone HTML for local delivery."""
import hashlib
import shutil
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
dist = root / "dist"
sdist = dist / f"pmut_haptics-{version}.tar.gz"
wheel = dist / f"pmut_haptics-{version}-py3-none-any.whl"
archive = dist / f"pmut-haptics-{version}-project.zip"
html = root / "pmut-haptics.html"
if not sdist.is_file() or not wheel.is_file():
    raise SystemExit("Build the wheel and sdist with uv build first.")

files = {}
with tarfile.open(sdist, "r:gz") as source:
    for member in source.getmembers():
        if not member.isfile():
            continue
        parts = PurePosixPath(member.name).parts
        if len(parts) < 2 or ".." in parts or parts[0] != f"pmut_haptics-{version}":
            raise ValueError(f"Unexpected archive path: {member.name}")
        content = source.extractfile(member)
        if content is None:
            raise ValueError(f"Missing archive content: {member.name}")
        files["/".join(parts[1:])] = content.read()

required = {"pmut-haptics.html", "web/core.js", "web/ui.js", "README.md",
            "docs/html.md", "tests/test_html.py", "tests/browser_probe.cjs",
            "web/vendor/plotly.min.js", "web/vendor/LICENSE-plotly.txt"}
if not required.issubset(files):
    raise ValueError(f"Source package is incomplete: {required - files.keys()}")
if files["pmut-haptics.html"] != html.read_bytes():
    raise ValueError("Source package has an old HTML; rebuild it before packaging.")

with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
    for name, content in sorted(files.items()):
        info = zipfile.ZipInfo("pmut-haptics/" + name, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        output.writestr(info, content, compresslevel=9)
shutil.copyfile(html, dist / html.name)
deliverables = [wheel, sdist, archive, dist / html.name]
manifest = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
                   for p in sorted(deliverables))
(dist / "checksums.sha256").write_text(manifest, encoding="utf-8")
for path in deliverables:
    print(f"{path.name}: {path.stat().st_size:,} bytes")
