import unittest
from datetime import datetime, timezone

import helpers  # noqa: F401
import signals
from sessions import Action, Session, Turn, classify


def at(hour, minute=0):
    return datetime(2026, 11, 10, hour, minute, tzinfo=timezone.utc)


def sample():
    first = Session("claude", "cc-1", "shop", "/a", at(9), at(9, 30), [
        Turn(at(9), "Let's plan the coupon feature first",
             [classify("Skill", "superpowers:brainstorming"), classify("Bash", "pytest")], "completed", 100),
        Turn(at(9, 10), "no, I meant the checkout coupon", [classify("Read")], "completed"),
        Turn(at(9, 20), "Why does the cart total fail with an error?", [classify("mcp__context7__query-docs")], "completed"),
    ])
    second = Session("codex", "cx-1", "api", "/b", at(11), at(11, 10), [
        Turn(at(11), "Add pagination to the users endpoint", [classify("spawn_agent")], "completed", 50),
        Turn(at(11, 5), "Add pagination to the users endpoint please", [], "interrupted"),
    ])
    return [first, second]


class FlagsTest(unittest.TestCase):
    def flags(self, text, previous=()):
        return signals.flags(Turn(None, text), list(previous))

    def test_flags(self):
        self.assertEqual(self.flags("no, I meant the other file"), ["correction"])
        self.assertEqual(self.flags("ні, я мав на увазі інший файл"), ["correction"])
        self.assertEqual(self.flags("чому це падає"), ["question"])
        self.assertEqual(self.flags("there is a traceback in the logs"), ["debug"])
        self.assertEqual(self.flags("make a plan for it"), ["plan"])
        self.assertEqual(self.flags("Add pagination to the users endpoint please",
                                    ["a", "b", "Add pagination to the users endpoint"]), ["repeat"])
        self.assertEqual(self.flags("ok", ["ok"]), [])

    def test_plan_action_flags_plan(self):
        self.assertEqual(signals.flags(Turn(None, "go", [Action("update_plan", "plan")]), []), ["plan"])


class SummaryTest(unittest.TestCase):
    def test_counts(self):
        summary = signals.summarize(sample())
        expected = dict(sessions=2, turns=5, requests=5, corrections=1, repeats=1, interrupted=1, completed_sessions=1,
                        abandoned=1, verifications=1, plan_first=1, questions=1, debug=1, short_requests=5,
                        big_requests=0, active_days=1, project_switches=1, read_actions=1, actions=5, subagent_turns=1,
                        skills={"superpowers:brainstorming": 1}, mcp={"context7": 1}, compactions=0, minutes=40,
                        tokens={"claude": 100, "codex": 50, "cursor": None},
                        projects={"shop": {"sessions": 1, "turns": 3}, "api": {"sessions": 1, "turns": 2}})

        for key, value in expected.items():
            self.assertEqual(summary[key], value, key)

        self.assertEqual(summary["kinds"], {"skill": 1, "test": 1, "read": 1, "mcp": 1, "subagent": 1})
        self.assertEqual((len(summary["by_weekday"]), sum(summary["by_weekday"])), (7, 5))
        self.assertEqual((len(summary["by_hour"]), sum(summary["by_hour"])), (24, 5))

    def test_only_checks_after_the_last_edit_count(self):
        edit = classify("apply_patch")
        check = classify("Bash", "pytest")
        sessions = []

        for actions in (([check],), ([check], [edit]), ([edit, check, edit],), ([edit], [check, check])):
            turns = [Turn(at(9, i), "Work", turn_actions) for i, turn_actions in enumerate(actions)]
            sessions.append(Session("codex", "cx-1", "shop", "/a", at(9), at(10), turns))

        summary = signals.summarize(sessions)
        self.assertEqual(summary["edit_sessions"], 3)
        self.assertEqual(summary["checks_after_edit_sessions"], 1)


class ScoresTest(unittest.TestCase):
    def assertScores(self, actual, expected):
        self.assertEqual(set(actual), set(expected))

        for key, value in expected.items():
            self.assertAlmostEqual(actual[key], value, delta=0.051, msg=key)

    def test_axes(self):
        self.assertScores(signals.axes(signals.summarize(sample())),
                          dict(clarity=0.0, focus=7.3, completion=4.0, tool_range=3.0))

    def test_archetypes(self):
        self.assertScores(signals.archetypes(signals.summarize(sample())),
                          dict(architect=7.0, sprinter=6.5, perfectionist=6.0, explorer=6.0, delegator=4.75, detective=5.0))

    def test_minutes_cap_idle_gaps(self):
        start = datetime(2026, 11, 10, 9, tzinfo=timezone.utc)
        later = datetime(2026, 11, 11, 9, tzinfo=timezone.utc)
        session = Session("claude", "cc-2", "shop", "/c", start, datetime(2026, 11, 11, 9, 10, tzinfo=timezone.utc),
                          [Turn(start, "first"), Turn(later, "next day")])
        self.assertEqual(signals.summarize([session])["minutes"], 40)

    def test_empty_input(self):
        summary = signals.summarize([])
        self.assertEqual(set(signals.axes(summary).values()) | set(signals.archetypes(summary).values()), {0.0})


if __name__ == "__main__":
    unittest.main()
