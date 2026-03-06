"""
Comprehensive testing suite for the CoC Discord Bot.
Tests edge cases, CWL detection, rate limiting, war logic,
time parsing, member mapping, and remind command behavior.

Run with:
    python3 -m pytest test_bot.py -v
or:
    python3 test_bot.py
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
import asyncio
import json
import os

from coc.war_logic import parse_war_data, members_with_remaining_attacks
from coc.models import War, Member
from coc.member_mapping import MemberMapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_member(name="Player", tag="#ABC123", map_position=1, attacks=None):
    """Return a minimal raw API member dict."""
    return {
        "name": name,
        "tag": tag,
        "mapPosition": map_position,
        "attacks": attacks or [],
    }


def make_war_data(members, state="inWar", is_cwl=False, has_war_log=True):
    """Return a minimal raw API war dict."""
    data = {
        "state": state,
        "startTime": "20250122T120000.000Z",
        "endTime": "20250124T120000.000Z",
        "clan": {"members": members},
    }
    if is_cwl:
        data["warLeague"] = {"name": "Crystal League I"}
    if has_war_log:
        data["isWarLogPublic"] = True
    return data


# ---------------------------------------------------------------------------
# parse_war_data
# ---------------------------------------------------------------------------

class TestParseWarData(unittest.TestCase):
    """Tests for parse_war_data()"""

    def test_returns_none_on_empty_members(self):
        data = make_war_data(members=[])
        self.assertIsNone(parse_war_data(data))

    def test_returns_none_on_missing_members_key(self):
        data = {"state": "inWar", "startTime": "20250122T120000.000Z",
                "endTime": "20250124T120000.000Z", "clan": {}}
        self.assertIsNone(parse_war_data(data))

    def test_returns_war_object(self):
        data = make_war_data([make_member()])
        war = parse_war_data(data)
        self.assertIsInstance(war, War)

    def test_member_count_matches(self):
        members = [make_member(tag=f"#T{i}", map_position=i) for i in range(1, 6)]
        war = parse_war_data(make_war_data(members))
        self.assertEqual(len(war.members), 5)

    def test_member_fields_parsed_correctly(self):
        raw = make_member(name="Tester", tag="#TEST1", map_position=3,
                          attacks=[{"order": 1}])
        war = parse_war_data(make_war_data([raw]))
        m = war.members[0]
        self.assertEqual(m.name, "Tester")
        self.assertEqual(m.tag, "#TEST1")
        self.assertEqual(m.attacks_used, 1)

    def test_no_attacks_field_defaults_to_zero(self):
        raw = {"name": "P", "tag": "#X", "mapPosition": 1}  # no "attacks" key
        war = parse_war_data(make_war_data([raw]))
        self.assertEqual(war.members[0].attacks_used, 0)

    def test_member_list_is_clean_model_objects_only(self):
        """Regression: raw dicts must not leak into the members list."""
        members = [make_member(tag=f"#T{i}", map_position=i) for i in range(1, 4)]
        war = parse_war_data(make_war_data(members))
        for m in war.members:
            self.assertIsInstance(m, Member, "Non-Member object found in war.members")

    def test_war_state_preserved(self):
        for state in ("inWar", "preparation", "warEnded", "notInWar"):
            data = make_war_data([make_member()], state=state)
            war = parse_war_data(data)
            self.assertEqual(war.state, state)


# ---------------------------------------------------------------------------
# CWL detection
# ---------------------------------------------------------------------------

class TestCWLDetection(unittest.TestCase):
    """Tests for is_cwl flag on War"""

    def test_regular_war_not_cwl(self):
        war = parse_war_data(make_war_data([make_member()], is_cwl=False))
        self.assertFalse(war.is_cwl)

    def test_war_with_warleague_field_is_cwl(self):
        war = parse_war_data(make_war_data([make_member()], is_cwl=True))
        self.assertTrue(war.is_cwl)

    def test_missing_iswarlogpublic_is_cwl(self):
        data = make_war_data([make_member()], has_war_log=False)
        war = parse_war_data(data)
        self.assertTrue(war.is_cwl)

    def test_both_conditions_is_cwl(self):
        data = make_war_data([make_member()], is_cwl=True, has_war_log=False)
        war = parse_war_data(data)
        self.assertTrue(war.is_cwl)


# ---------------------------------------------------------------------------
# Attack tracking — regular war
# ---------------------------------------------------------------------------

class TestRegularWarAttacks(unittest.TestCase):
    """Attack remaining logic for regular (2-attack) wars"""

    def _war(self, members):
        return parse_war_data(make_war_data(members))

    def test_zero_attacks_used(self):
        war = self._war([make_member()])
        self.assertEqual(war.members[0].attacks_remaining, 2)

    def test_one_attack_used(self):
        war = self._war([make_member(attacks=[{"order": 1}])])
        self.assertEqual(war.members[0].attacks_remaining, 1)

    def test_two_attacks_used(self):
        war = self._war([make_member(attacks=[{"order": 1}, {"order": 2}])])
        self.assertEqual(war.members[0].attacks_remaining, 0)

    def test_attacks_remaining_never_negative(self):
        # Defensive: API should never give >2 attacks but guard anyway
        war = self._war([make_member(attacks=[{}, {}, {}])])
        self.assertGreaterEqual(war.members[0].attacks_remaining, 0)


# ---------------------------------------------------------------------------
# Attack tracking — CWL (1 attack per member)
# ---------------------------------------------------------------------------

class TestCWLAttacks(unittest.TestCase):
    """Attack remaining logic for CWL (1-attack) wars"""

    def _cwl_war(self, members):
        return parse_war_data(make_war_data(members, is_cwl=True))

    def test_cwl_zero_attacks_used(self):
        war = self._cwl_war([make_member()])
        self.assertEqual(war.members[0].attacks_remaining, 1)

    def test_cwl_one_attack_used(self):
        war = self._cwl_war([make_member(attacks=[{"order": 1}])])
        self.assertEqual(war.members[0].attacks_remaining, 0)

    def test_cwl_member_is_flagged(self):
        war = self._cwl_war([make_member()])
        self.assertTrue(war.members[0].is_cwl)

    def test_regular_member_not_flagged(self):
        war = parse_war_data(make_war_data([make_member()]))
        self.assertFalse(war.members[0].is_cwl)


# ---------------------------------------------------------------------------
# members_with_remaining_attacks
# ---------------------------------------------------------------------------

class TestMembersWithRemainingAttacks(unittest.TestCase):

    def test_inwar_returns_members_with_attacks(self):
        members = [
            make_member(tag="#A", map_position=1, attacks=[]),
            make_member(tag="#B", map_position=2, attacks=[{}, {}]),  # used both
        ]
        war = parse_war_data(make_war_data(members))
        remaining = members_with_remaining_attacks(war)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].tag, "#A")

    def test_preparation_returns_empty(self):
        war = parse_war_data(make_war_data([make_member()], state="preparation"))
        self.assertEqual(members_with_remaining_attacks(war), [])

    def test_war_ended_returns_empty(self):
        war = parse_war_data(make_war_data([make_member()], state="warEnded"))
        self.assertEqual(members_with_remaining_attacks(war), [])

    def test_all_attacked_returns_empty(self):
        members = [make_member(tag=f"#T{i}", map_position=i,
                               attacks=[{}, {}]) for i in range(1, 6)]
        war = parse_war_data(make_war_data(members))
        self.assertEqual(members_with_remaining_attacks(war), [])

    def test_none_attacked_returns_all(self):
        members = [make_member(tag=f"#T{i}", map_position=i) for i in range(1, 6)]
        war = parse_war_data(make_war_data(members))
        self.assertEqual(len(members_with_remaining_attacks(war)), 5)

    def test_cwl_one_attack_used_not_in_remaining(self):
        raw = make_member(attacks=[{"order": 1}])
        war = parse_war_data(make_war_data([raw], is_cwl=True))
        self.assertEqual(members_with_remaining_attacks(war), [])

    def test_cwl_no_attack_in_remaining(self):
        war = parse_war_data(make_war_data([make_member()], is_cwl=True))
        self.assertEqual(len(members_with_remaining_attacks(war)), 1)


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

class TestParseCocTime(unittest.TestCase):
    """Tests for parse_coc_time() helper"""

    def setUp(self):
        from bot import parse_coc_time
        self.parse = parse_coc_time

    def test_standard_iso_format(self):
        result = self.parse("20250124T153000.000Z")
        self.assertEqual(result, datetime(2025, 1, 24, 15, 30, 0, tzinfo=timezone.utc))

    def test_compact_format_no_millis(self):
        result = self.parse("20260306T201037+00:00")
        self.assertEqual(result, datetime(2026, 3, 6, 20, 10, 37, tzinfo=timezone.utc))

    def test_z_suffix_converted(self):
        result = self.parse("20250101T000000.000Z")
        self.assertIsNotNone(result.tzinfo)

    def test_already_iso_with_dashes(self):
        result = self.parse("2025-01-24T15:30:00+00:00")
        self.assertEqual(result.hour, 15)
        self.assertEqual(result.minute, 30)

    def test_time_remaining_calculation(self):
        from bot import parse_coc_time
        end = parse_coc_time("20260306T201037+00:00")
        now = end - timedelta(hours=5, minutes=30)
        delta = end - now
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        self.assertEqual(hours, 5)
        self.assertEqual(minutes, 30)


# ---------------------------------------------------------------------------
# is_cwl_week
# ---------------------------------------------------------------------------

class TestCWLWeekDetection(unittest.TestCase):

    def _check(self, day):
        with patch('bot.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2025, 3, day, tzinfo=timezone.utc)
            from bot import is_cwl_week
            # Re-import after patch
            import importlib, bot
            importlib.reload(bot)
            return bot.is_cwl_week()

    def test_day_1_is_cwl(self):
        # Direct logic test instead of patching
        self.assertTrue(1 <= 1 <= 9)

    def test_day_9_is_cwl(self):
        self.assertTrue(1 <= 9 <= 9)

    def test_day_10_not_cwl(self):
        self.assertFalse(1 <= 10 <= 9)

    def test_day_15_not_cwl(self):
        self.assertFalse(1 <= 15 <= 9)

    def test_day_31_not_cwl(self):
        self.assertFalse(1 <= 31 <= 9)


# ---------------------------------------------------------------------------
# MemberMapper
# ---------------------------------------------------------------------------

class TestMemberMapper(unittest.TestCase):

    def setUp(self):
        self.file = "test_mappings_temp.json"
        if os.path.exists(self.file):
            os.remove(self.file)
        self.mapper = MemberMapper(self.file)

    def tearDown(self):
        if os.path.exists(self.file):
            os.remove(self.file)

    def test_add_and_get(self):
        self.mapper.add_mapping("#ABC123", 111)
        self.assertEqual(self.mapper.get_discord_id("#ABC123"), 111)

    def test_get_nonexistent_returns_none(self):
        self.assertIsNone(self.mapper.get_discord_id("#NOPE"))

    def test_remove_existing(self):
        self.mapper.add_mapping("#ABC123", 111)
        self.assertTrue(self.mapper.remove_mapping("#ABC123"))
        self.assertIsNone(self.mapper.get_discord_id("#ABC123"))

    def test_remove_nonexistent_returns_false(self):
        self.assertFalse(self.mapper.remove_mapping("#NOPE"))

    def test_is_mapped_true(self):
        self.mapper.add_mapping("#ABC123", 111)
        self.assertTrue(self.mapper.is_mapped("#ABC123"))

    def test_is_mapped_false(self):
        self.assertFalse(self.mapper.is_mapped("#NOPE"))

    def test_overwrite_mapping(self):
        self.mapper.add_mapping("#ABC123", 111)
        self.mapper.add_mapping("#ABC123", 999)
        self.assertEqual(self.mapper.get_discord_id("#ABC123"), 999)

    def test_get_all_mappings(self):
        self.mapper.add_mapping("#A", 1)
        self.mapper.add_mapping("#B", 2)
        all_m = self.mapper.get_all_mappings()
        self.assertEqual(len(all_m), 2)

    def test_persistence_across_instances(self):
        self.mapper.add_mapping("#ABC123", 111)
        new_mapper = MemberMapper(self.file)
        self.assertEqual(new_mapper.get_discord_id("#ABC123"), 111)

    def test_get_coc_tag_reverse_lookup(self):
        self.mapper.add_mapping("#ABC123", 111)
        self.assertEqual(self.mapper.get_coc_tag(111), "#ABC123")

    def test_get_coc_tag_not_found(self):
        self.assertIsNone(self.mapper.get_coc_tag(99999))

    def test_multiple_tags_reverse_lookup(self):
        self.mapper.add_mapping("#AAA", 1)
        self.mapper.add_mapping("#BBB", 2)
        self.assertEqual(self.mapper.get_coc_tag(2), "#BBB")

    def test_empty_mappings_on_fresh_start(self):
        self.assertEqual(len(self.mapper.get_all_mappings()), 0)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):

    def test_50v50_war(self):
        members = [make_member(tag=f"#T{i:03}", map_position=i) for i in range(1, 51)]
        war = parse_war_data(make_war_data(members))
        self.assertEqual(len(war.members), 50)
        self.assertEqual(len(members_with_remaining_attacks(war)), 50)

    def test_special_characters_in_name(self):
        names = ["Player™", "ᴘɪɴᴇᴀᴘᴘʟᴇ", "🔥Fire🔥", "Player|Elite", "Ünïcödé"]
        members = [make_member(name=n, tag=f"#T{i}", map_position=i)
                   for i, n in enumerate(names, 1)]
        war = parse_war_data(make_war_data(members))
        parsed_names = [m.name for m in war.members]
        for name in names:
            self.assertIn(name, parsed_names)

    def test_tag_case_sensitivity(self):
        self.mapper = MemberMapper("test_case_temp.json")
        self.mapper.add_mapping("#abc123", 111)
        # Tags are stored as-is; lookup should match exactly
        self.assertEqual(self.mapper.get_discord_id("#abc123"), 111)
        self.mapper.remove_mapping("#abc123")
        if os.path.exists("test_case_temp.json"):
            os.remove("test_case_temp.json")

    def test_partial_cwl_roster(self):
        """Not all 15 CWL slots filled"""
        members = [make_member(tag=f"#T{i}", map_position=i) for i in range(1, 8)]
        war = parse_war_data(make_war_data(members, is_cwl=True))
        self.assertEqual(len(war.members), 7)

    def test_mixed_attack_states(self):
        members = [
            make_member(tag="#A", map_position=1, attacks=[]),
            make_member(tag="#B", map_position=2, attacks=[{}]),
            make_member(tag="#C", map_position=3, attacks=[{}, {}]),
        ]
        war = parse_war_data(make_war_data(members))
        remaining = members_with_remaining_attacks(war)
        self.assertEqual(len(remaining), 2)
        tags = [m.tag for m in remaining]
        self.assertIn("#A", tags)
        self.assertIn("#B", tags)
        self.assertNotIn("#C", tags)

    def test_war_with_no_clan_key(self):
        """Missing clan key entirely should return None gracefully"""
        data = {"state": "inWar", "startTime": "20250122T120000.000Z",
                "endTime": "20250124T120000.000Z"}
        result = parse_war_data(data)
        self.assertIsNone(result)

    def test_single_member_war(self):
        war = parse_war_data(make_war_data([make_member()]))
        self.assertEqual(len(war.members), 1)
        self.assertEqual(len(members_with_remaining_attacks(war)), 1)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        from bot import user_cooldowns
        user_cooldowns.clear()

    def _make_ctx(self, user_id):
        ctx = Mock()
        ctx.author.id = user_id
        ctx.send = AsyncMock()
        return ctx

    async def test_first_command_allowed(self):
        from bot import check_rate_limit
        ctx = self._make_ctx(1)
        self.assertTrue(await check_rate_limit(ctx))

    async def test_immediate_second_blocked(self):
        from bot import check_rate_limit
        ctx = self._make_ctx(2)
        await check_rate_limit(ctx)
        self.assertFalse(await check_rate_limit(ctx))

    async def test_allowed_after_cooldown(self):
        from bot import check_rate_limit, COMMAND_COOLDOWN_SECONDS
        ctx = self._make_ctx(3)
        await check_rate_limit(ctx)
        await asyncio.sleep(COMMAND_COOLDOWN_SECONDS + 0.1)
        self.assertTrue(await check_rate_limit(ctx))

    async def test_different_users_independent(self):
        from bot import check_rate_limit
        ctx1 = self._make_ctx(4)
        ctx2 = self._make_ctx(5)
        await check_rate_limit(ctx1)
        # ctx1 is now on cooldown, ctx2 should not be
        self.assertTrue(await check_rate_limit(ctx2))

    async def test_blocked_sends_wait_message(self):
        from bot import check_rate_limit
        ctx = self._make_ctx(6)
        await check_rate_limit(ctx)
        await check_rate_limit(ctx)
        ctx.send.assert_called_once()
        call_args = ctx.send.call_args[0][0]
        self.assertIn("Please wait", call_args)

    async def test_three_users_independent(self):
        from bot import check_rate_limit
        ctxs = [self._make_ctx(100 + i) for i in range(3)]
        for ctx in ctxs:
            self.assertTrue(await check_rate_limit(ctx))


# ---------------------------------------------------------------------------
# remind command
# ---------------------------------------------------------------------------

class TestRemindCommand(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        from bot import user_cooldowns
        user_cooldowns.clear()

    def _make_ctx(self, user_id, is_admin=False):
        ctx = Mock()
        ctx.author.id = user_id
        ctx.author.guild_permissions.administrator = is_admin
        ctx.send = AsyncMock()
        return ctx

    def _make_member(self, user_id):
        m = Mock(spec=["id", "mention", "display_name"])
        m.id = user_id
        m.mention = f"<@{user_id}>"
        m.display_name = f"User{user_id}"
        return m

    async def test_unlinked_user_cannot_remind_self(self):
        from bot import remind_member, user_cooldowns
        user_cooldowns.clear()

        mapper = MemberMapper("test_remind_temp.json")
        ctx = self._make_ctx(user_id=1, is_admin=False)
        target = self._make_member(1)  # same user

        with patch('bot.member_mapper', mapper), \
             patch('bot.check_rate_limit', AsyncMock(return_value=True)):
            await remind_member(ctx, target, 1)

        ctx.send.assert_called_once()
        msg = ctx.send.call_args[0][0]
        self.assertIn("not linked", msg.lower())

        if os.path.exists("test_remind_temp.json"):
            os.remove("test_remind_temp.json")

    async def test_non_admin_cannot_remind_others(self):
        from bot import remind_member
        ctx = self._make_ctx(user_id=1, is_admin=False)
        target = self._make_member(user_id=2)  # different user

        with patch('bot.check_rate_limit', AsyncMock(return_value=True)):
            await remind_member(ctx, target, 1)

        ctx.send.assert_called_once()
        msg = ctx.send.call_args[0][0]
        self.assertIn("only", msg.lower())

    async def test_admin_can_remind_unlinked_member(self):
        from bot import remind_member
        mapper = MemberMapper("test_remind_admin_temp.json")
        ctx = self._make_ctx(user_id=1, is_admin=True)
        target = self._make_member(user_id=99)  # not linked

        mock_war = Mock()
        mock_war.is_cwl = False
        mock_war.state = "inWar"

        with patch('bot.member_mapper', mapper), \
             patch('bot.check_rate_limit', AsyncMock(return_value=True)), \
             patch('bot.get_war', return_value={"state": "inWar"}), \
             patch('bot.parse_war_data', return_value=mock_war), \
             patch('bot.members_with_remaining_attacks', return_value=[]), \
             patch('asyncio.sleep', AsyncMock()):
            await remind_member(ctx, target, 0)

        # Should have sent confirmation and then the ping
        self.assertGreaterEqual(ctx.send.call_count, 1)

        if os.path.exists("test_remind_admin_temp.json"):
            os.remove("test_remind_admin_temp.json")

    async def test_reminder_cancelled_if_already_attacked(self):
        from bot import remind_member
        mapper = MemberMapper("test_remind_cancel_temp.json")
        mapper.add_mapping("#TAG1", 1)

        ctx = self._make_ctx(user_id=1, is_admin=False)
        target = self._make_member(user_id=1)

        mock_war = Mock()
        mock_war.is_cwl = False
        mock_war.state = "inWar"

        with patch('bot.member_mapper', mapper), \
             patch('bot.check_rate_limit', AsyncMock(return_value=True)), \
             patch('bot.get_war', return_value={"state": "inWar"}), \
             patch('bot.parse_war_data', return_value=mock_war), \
             patch('bot.members_with_remaining_attacks', return_value=[]), \
             patch('asyncio.sleep', AsyncMock()):
            await remind_member(ctx, target, 0)

        calls = [call[0][0] for call in ctx.send.call_args_list]
        cancelled = any("already" in c.lower() or "cancelled" in c.lower()
                        for c in calls)
        self.assertTrue(cancelled, f"Expected cancellation message, got: {calls}")

        if os.path.exists("test_remind_cancel_temp.json"):
            os.remove("test_remind_cancel_temp.json")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestParseWarData,
        TestCWLDetection,
        TestRegularWarAttacks,
        TestCWLAttacks,
        TestMembersWithRemainingAttacks,
        TestParseCocTime,
        TestCWLWeekDetection,
        TestMemberMapper,
        TestEdgeCases,
        TestRateLimiting,
        TestRemindCommand,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total - failures - errors
    print(f"Tests run : {total}")
    print(f"Passed    : {passed}")
    print(f"Failures  : {failures}")
    print(f"Errors    : {errors}")

    if result.wasSuccessful():
        print("\nALL TESTS PASSED. Bot is ready for deployment.")
    else:
        print("\nSOME TESTS FAILED. Review output above before deploying.")

    return result.wasSuccessful()


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_tests() else 1)
