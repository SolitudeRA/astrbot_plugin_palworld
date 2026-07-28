"""Generate the six localized README card screenshots from the production renderer."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from palworld_terminal.adapters.icon_repository import IconRepository  # noqa: E402
from palworld_terminal.application.dtos import CompanionView, MeCardDTO  # noqa: E402
from palworld_terminal.presentation.card_render import build_me_card_html  # noqa: E402
from palworld_terminal.presentation.locale import load_locale  # noqa: E402

ICON_DIR = ROOT / "assets" / "element-icons"
NODE_RENDERER = ROOT / "frontend" / "scripts" / "render-docs-cards.mjs"
LOCALES = ("zh-CN", "ja", "en")
THEMES = ("light", "dark")

DEMO_CARD = MeCardDTO(
    name="player-01",
    level=42,
    online=True,
    online_seconds=7_540,
    guild_name="Ops A",
    hidden=False,
    today_seconds=7_200,
    total_seconds=441_000,
    percentile=87.0,
    last_seen_at=0,
    first_seen_at=32,
    companion=CompanionView(
        species_name="Lamball",
        element="neutral",
        level=38,
        action_label="working",
        hp_ratio=0.86,
    ),
    companion_status="shown",
)


def _load_icons() -> dict[str, str]:
    repository = IconRepository(ICON_DIR)
    repository.load()
    return repository.icons()


def render_card_html(locale: str, theme: str, *, icons: dict[str, str] | None = None) -> str:
    """Load one locale and invoke the real production card builder."""
    if locale not in LOCALES:
        raise ValueError(f"unsupported locale: {locale}")
    if theme not in THEMES:
        raise ValueError(f"unsupported theme: {theme}")
    load_locale(locale)
    return build_me_card_html(DEMO_CARD, _load_icons() if icons is None else icons, theme)


def prepare_card_jobs(html_dir: Path, output_dir: Path) -> list[dict[str, str]]:
    """Write deterministic production HTML inputs and return six browser jobs."""
    html_dir.mkdir(parents=True, exist_ok=False)
    jobs: list[dict[str, str]] = []
    icons = _load_icons()
    try:
        for locale in LOCALES:
            for theme in THEMES:
                prefix = "" if locale == "zh-CN" else f"{locale}/"
                output = f"{prefix}me-card-{theme}.png"
                html_path = html_dir / locale / f"me-card-{theme}.html"
                html_path.parent.mkdir(parents=True, exist_ok=True)
                html_path.write_text(render_card_html(locale, theme, icons=icons), encoding="utf-8", newline="\n")
                jobs.append(
                    {
                        "locale": locale,
                        "theme": theme,
                        "output": output,
                        "htmlPath": str(html_path.resolve()),
                        "outputPath": str((output_dir / Path(output)).resolve()),
                    }
                )
    finally:
        load_locale("zh-CN")
    return jobs


def _run_renderer(jobs_file: Path, *, node: str = "node") -> dict[str, Any]:
    completed = subprocess.run(
        [node, str(NODE_RENDERER), "--jobs-file", str(jobs_file)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"card renderer failed: {detail}")
    return json.loads(completed.stdout)


def export_cards(output_dir: Path, *, node: str = "node") -> dict[str, Any]:
    """Render all six cards into a previously absent output directory."""
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(prefix="palword-card-html-") as temp:
            html_dir = Path(temp) / "html"
            jobs = prepare_card_jobs(html_dir, output_dir)
            jobs_file = Path(temp) / "jobs.json"
            jobs_file.write_text(
                json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            result = _run_renderer(jobs_file, node=node)
        if len(result.get("captures", [])) != 6:
            raise RuntimeError("card renderer did not return exactly six captures")
        return {"outputDir": str(output_dir), **result}
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise
    finally:
        load_locale("zh-CN")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--node", default="node")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    print(json.dumps(export_cards(args.output_dir, node=args.node), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
