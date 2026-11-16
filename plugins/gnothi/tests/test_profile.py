import json
import unittest
from datetime import date
from unittest import mock

from helpers import PLUGIN, TempHome
from test_cli import run
import profiles


def axis(ident, name=None):
    return {"id": ident, "name": name or ident.title(), "measures": f"How {ident} goes", "signals": ["corrections"]}


AXES = [axis("framing"), axis("verification"), axis("debugging"), axis("context")]


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)

    def test_defaults_without_file(self):
        self.assertEqual(profiles.read(), {"schema_version": 1, "epochs": [],
                                           "options": {"archetypes": False, "metrics_only": False, "period": "month"}})
        self.assertIsNone(profiles.current_epoch(profiles.read()))

    def test_new_axes_start_epoch(self):
        with mock.patch("profiles.date") as clock:
            clock.today.return_value = date(2026, 11, 16)
            profiles.set_axes(AXES, "I build web shops", "developer")
            profile = profiles.set_axes(AXES[:3] + [axis("reuse")], "I build web shops", None)

        self.assertEqual([epoch["id"] for epoch in profile["epochs"]], [1, 2])
        epoch = profiles.current_epoch(profiles.read())
        self.assertEqual((epoch["id"], epoch["started"], epoch["axes"][-1]["id"]), (2, "2026-11-16", "reuse"))

    def test_same_axes_keep_epoch(self):
        profiles.set_axes(AXES, "first", None)
        profile = profiles.set_axes(AXES, "second", None)
        self.assertEqual(len(profile["epochs"]), 1)
        self.assertEqual(profile["epochs"][0]["description"], "second")

    def test_rejects_three_or_seven_axes(self):
        for axes in (AXES[:3], AXES + [axis("a1"), axis("a2"), axis("a3")]):
            with self.assertRaisesRegex(ValueError, "4–6"):
                profiles.set_axes(axes, "x", None)

    def test_rejects_bad_axes(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            profiles.set_axes(AXES[:3] + [axis("framing")], "x", None)

        with self.assertRaisesRegex(ValueError, "id"):
            profiles.set_axes(AXES[:3] + [axis("Bad Id")], "x", None)

        with self.assertRaisesRegex(ValueError, "measures"):
            profiles.set_axes(AXES[:3] + [{"id": "empty", "name": "Empty"}], "x", None)

    def test_options_persist(self):
        profiles.set_options(archetypes=True, period="year")
        self.assertEqual(profiles.read()["options"], {"archetypes": True, "metrics_only": False, "period": "year"})

        with self.assertRaises(ValueError):
            profiles.set_options(period="week")

    def test_templates_are_valid(self):
        found = profiles.templates()
        self.assertEqual(set(found), {"developer", "designer", "pm", "qa"})

        for template in found.values():
            profiles.validate_axes(template["axes"])
            self.assertTrue(template["name"] and template["description"])


class ProfileCliTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome().__enter__()
        self.addCleanup(self.home.__exit__)

    def test_set_show_and_options(self):
        path = self.home.root / "axes.json"
        path.write_text(json.dumps({"description": "web shops", "template": "developer", "axes": AXES}))
        self.assertEqual(run("profile", "set", "--file", str(path))[0], 0)
        code, result = run("profile", "show")
        self.assertEqual((code, result["epoch"]["id"], len(result["epoch"]["axes"])), (0, 1, 4))
        self.assertEqual(result["data_root"], str(self.home.root / "data"))
        run("profile", "options", "--archetypes", "on", "--period", "half")
        self.assertEqual(run("profile", "show")[1]["profile"]["options"]["archetypes"], True)
        self.assertEqual(set(run("profile", "templates")[1]["templates"]), {"developer", "designer", "pm", "qa"})

    def test_bad_file_fails(self):
        path = self.home.root / "axes.json"
        path.write_text(json.dumps({"axes": AXES[:2]}))
        code, result = run("profile", "set", "--file", str(path))
        self.assertEqual((code, result["status"]), (2, "FAIL"))

    def test_collect_uses_saved_options(self):
        from test_loading import install_fixtures

        install_fixtures(self.home)
        profiles.set_options(archetypes=True, period="all")
        code, result = run("collect")
        self.assertEqual((code, result["period"]["name"]), (0, "all"))
        self.assertIsNotNone(result["current"]["archetypes"])
        run("collect", "--period", "year")
        self.assertEqual(profiles.read()["options"]["period"], "year")


if __name__ == "__main__":
    unittest.main()
