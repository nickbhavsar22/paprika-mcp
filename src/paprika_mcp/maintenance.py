"""Maintenance CLI for auditing and repairing Paprika recipes."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from paprika_recipes.remote import RemoteRecipe

from .recipe_maintenance import RecipePlan, build_recipe_plan
from .utils import get_remote

logger = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _load_recipes(remote) -> list[RemoteRecipe]:
    return [recipe for recipe in remote.recipes if not recipe.in_trash]


def _make_default_output_dir() -> Path:
    root = Path.home() / ".paprika-mcp" / "maintenance"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_markdown_report(path: Path, plans: list[RecipePlan]) -> None:
    lines = ["# Paprika Recipe Audit", ""]
    for plan in plans:
        audit = plan.audit
        if audit is None:
            continue
        lines.append(f"## {plan.name}")
        lines.append(f"- UID: `{plan.uid}`")
        lines.append(f"- Status: `{audit.status}`")
        lines.append(f"- Has thumbnail: {'yes' if audit.has_thumbnail else 'no'}")
        if audit.thumbnail:
            lines.append(
                f"- Thumbnail candidate: `{audit.thumbnail.source}` `{audit.thumbnail.url}`"
            )
        for finding in audit.findings:
            lines.append(f"- {finding.severity.upper()}: {finding.message}")
        if plan.updates:
            lines.append("- Planned updates:")
            for field, value in plan.updates.items():
                lines.append(f"  - `{field}`")
                lines.append(f"    - `{str(value)[:200]}`")
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_backup(recipe: RemoteRecipe, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{recipe.uid}.json"
    _write_json(backup_path, recipe.as_dict())
    return backup_path


def _apply_plan(
    remote, recipe: RemoteRecipe, plan: RecipePlan, backup_dir: Path
) -> list[str]:
    applied_fields: list[str] = []
    _write_backup(recipe, backup_dir)

    for field, value in plan.updates.items():
        setattr(recipe, field, value)
        applied_fields.append(field)

    if applied_fields:
        remote.upload_recipe(recipe)

    return applied_fields


def audit_recipes(
    *,
    limit: int | None = None,
    recipe_id: str | None = None,
    title: str | None = None,
) -> list[RecipePlan]:
    """Audit recipes and return concrete remediation plans."""
    remote = get_remote()
    recipes = _load_recipes(remote)

    if recipe_id:
        recipes = [recipe for recipe in recipes if recipe.uid == recipe_id]
    if title:
        title_lower = title.lower()
        recipes = [recipe for recipe in recipes if recipe.name.lower() == title_lower]
    if limit is not None:
        recipes = recipes[:limit]

    plans = [build_recipe_plan(recipe) for recipe in recipes]
    return plans


def run_audit_command(args: argparse.Namespace) -> int:
    plans = audit_recipes(limit=args.limit, recipe_id=args.recipe_id, title=args.title)

    output_dir = (
        Path(args.output_dir) if args.output_dir else _make_default_output_dir()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()

    json_path = (
        Path(args.output) if args.output else output_dir / f"audit-{timestamp}.json"
    )
    markdown_path = (
        Path(args.markdown_output)
        if args.markdown_output
        else output_dir / f"audit-{timestamp}.md"
    )

    counts = {
        "total": len(plans),
        "safe_to_auto_fix": sum(
            1
            for plan in plans
            if plan.audit and plan.audit.status == "safe_to_auto_fix"
        ),
        "needs_review": sum(
            1 for plan in plans if plan.audit and plan.audit.status == "needs_review"
        ),
        "leave_unchanged": sum(
            1 for plan in plans if plan.audit and plan.audit.status == "leave_unchanged"
        ),
    }

    payload = {
        "generated_at": timestamp,
        "recipes": [asdict(plan) for plan in plans],
        "counts": counts,
    }

    _write_json(json_path, payload)
    _write_markdown_report(markdown_path, plans)

    print(f"Audit written to {json_path}")
    print(f"Markdown written to {markdown_path}")
    print(
        "Counts: "
        f"total={counts['total']}, "
        f"safe={counts['safe_to_auto_fix']}, "
        f"review={counts['needs_review']}, "
        f"unchanged={counts['leave_unchanged']}"
    )
    return 0


def run_apply_command(args: argparse.Namespace) -> int:
    plans = audit_recipes(limit=args.limit, recipe_id=args.recipe_id, title=args.title)
    remote = get_remote()
    recipes_by_uid = {recipe.uid: recipe for recipe in _load_recipes(remote)}
    timestamp = _timestamp()
    output_dir = (
        Path(args.output_dir) if args.output_dir else _make_default_output_dir()
    )
    backup_dir = output_dir / f"backups-{timestamp}"
    results: list[dict[str, Any]] = []

    for plan in plans:
        recipe = recipes_by_uid.get(plan.uid)
        if recipe is None:
            continue

        if (
            plan.audit
            and plan.audit.status != "safe_to_auto_fix"
            and not args.include_review
        ):
            results.append(
                {
                    "uid": plan.uid,
                    "name": plan.name,
                    "status": plan.audit.status,
                    "planned_fields": sorted(plan.updates.keys()),
                    "applied": False,
                    "skipped": "requires_review",
                }
            )
            continue

        result: dict[str, object] = {
            "uid": plan.uid,
            "name": plan.name,
            "status": plan.audit.status if plan.audit else "unknown",
            "planned_fields": sorted(plan.updates.keys()),
        }

        if args.dry_run:
            result["applied"] = False
        else:
            applied_fields = _apply_plan(remote, recipe, plan, backup_dir)
            result["applied"] = bool(applied_fields)
            result["applied_fields"] = applied_fields

        results.append(result)

    report_path = (
        Path(args.output) if args.output else output_dir / f"apply-{timestamp}.json"
    )
    _write_json(report_path, {"generated_at": timestamp, "results": results})

    applied_count = sum(1 for item in results if item.get("applied"))
    print(f"Apply report written to {report_path}")
    print(f"Recipes processed: {len(results)}")
    print(f"Recipes applied: {applied_count}")
    if args.dry_run:
        print("Dry run only; no recipe was written back.")
    else:
        print(f"Backups written to {backup_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paprika-mcp-maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Audit recipes and write reports")
    audit.add_argument("--limit", type=int, default=None)
    audit.add_argument("--recipe-id", default=None)
    audit.add_argument("--title", default=None)
    audit.add_argument("--output", default=None)
    audit.add_argument("--markdown-output", default=None)
    audit.add_argument("--output-dir", default=None)
    audit.set_defaults(func=run_audit_command)

    apply_parser = subparsers.add_parser("apply", help="Apply safe recipe repairs")
    apply_parser.add_argument("--limit", type=int, default=None)
    apply_parser.add_argument("--recipe-id", default=None)
    apply_parser.add_argument("--title", default=None)
    apply_parser.add_argument("--output", default=None)
    apply_parser.add_argument("--output-dir", default=None)
    apply_parser.add_argument(
        "--include-review",
        action="store_true",
        default=False,
        help="Also apply changes that are flagged for manual review",
    )
    apply_parser.add_argument("--apply", action="store_true", default=False)
    apply_parser.set_defaults(func=run_apply_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.dry_run = not getattr(args, "apply", False)
    return int(args.func(args))
