#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from dependency_support import PLUGIN, bundle_path, data_root, installed

TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
# Playwright CLI run-code script: injects the pinned axe-core and returns a compact violation list.
TEMPLATE = """async page => {
  await page.addScriptTag({ content: %(source)s });
  return await page.evaluate(async ({ include, tags }) => {
    const result = await window.axe.run(include || document, { runOnly: { type: 'tag', values: tags } });
    return result.violations.map(v => ({
      id: v.id, impact: v.impact, help: v.help, url: v.helpUrl,
      nodes: v.nodes.slice(0, 10).map(n => ({ target: n.target, summary: n.failureSummary }))
    }));
  }, { include: %(include)s, tags: %(tags)s });
}
"""


def axe_source():
    source = PLUGIN / "dependencies/browser"
    folder = bundle_path(source, data_root(), "browser")
    path = folder / "node_modules/axe-core/axe.min.js"

    if not installed(source, folder) or not path.is_file():
        raise ValueError("Ready Check browser tools with axe-core are not installed; run the consent/setup command")

    return path.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Write a Playwright CLI run-code script that runs the pinned axe-core.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include", help="CSS selector of the changed component; default is the whole page")
    args = parser.parse_args()

    try:
        script = TEMPLATE % dict(source=json.dumps(axe_source()), include=json.dumps(args.include), tags=json.dumps(TAGS))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(script, encoding="utf-8")
        print(json.dumps(dict(status="PASS", script=str(args.output), tags=TAGS)))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps(dict(status="FAIL", reason=str(error))))
        return 2


if __name__ == "__main__":
    sys.exit(main())
