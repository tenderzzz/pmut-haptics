"""Build a self-contained, portable single-file HTML from maintained web sources."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
web = root / "web"
html = (web / "template.html").read_text(encoding="utf-8")
for token, filename in [
    ("/*__STYLE__*/", "style.css"),
    ("/*__PLOTLY_LICENSE__*/", "vendor/LICENSE-plotly.txt"),
    ("/*__PLOTLY__*/", "vendor/plotly.min.js"),
    ("/*__CORE__*/", "core.js"),
    ("/*__TASKS__*/", "tasks.js"),
    ("/*__LIBRARY__*/", "library.js"),
    ("/*__LAB__*/", "lab.js"),
    ("/*__UI__*/", "ui.js"),
]:
    content = (web / filename).read_text(encoding="utf-8")
    if filename.endswith(".js") and "</script" in content.lower():
        raise ValueError("Inline script contains an HTML closing tag")
    if html.count(token) != 1:
        raise ValueError(f"Missing or duplicate build token: {token}")
    html = html.replace(token, content)
output = root / "pmut-haptics.html"
output.write_text(html, encoding="utf-8")
print(f"Built {output.name}: {output.stat().st_size:,} bytes. No external runtime dependencies.")
