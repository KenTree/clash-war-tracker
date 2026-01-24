# test_bot.py
"""
Comprehensive testing suite for the CoC Discord Bot.
Tests edge cases, CWL detection, rate limiting, and war logic.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import asyncio
import json
import os

# Import modules to test
from coc.war_logic import parse_war_data, members_with_remaining_attacks
from coc.models import War, Member
from coc.member_mapping import MemberMapper


class TestCWLDetection(unittest.TestCase):
    """Test CWL war detection logic"""
    
    def test_regular_war_detection(self):
        """Regular war should NOT be detected as CWL"""
        regular_war_data = {
            "state": "inWar",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {
                        "name": "Player1",
                        "tag": "#ABC123",
                        "mapPosition": 1,
                        "attacks": []
                    }
                ]
            }
        }
        
        war = parse_war_data(regular_war_data)
        self.assertFalse(war.is_cwl, "Regular war incorrectly detected as CWL")
    
    def test_cwl_war_detection_missing_field(self):
        """CWL war (missing isWarLogPublic) should be detected"""
        cwl_war_data = {
            "state": "inWar",
            "startTime": "20250105T120000.000Z",
            "endTime": "20250106T120000.000Z",
            "clan": {
                "members": [
                    {
                        "name": "Player1",
                        "tag": "#ABC123",
                        "mapPosition": 1,
                        "attacks": []
                    }
                ]
            }
        }
        
        war = parse_war_data(cwl_war_data)
        self.assertTrue(war.is_cwl, "CWL war not detected (missing isWarLogPublic)")
    
    def test_cwl_war_detection_warleague_field(self):
        """CWL war (with warLeague field) should be detected"""
        cwl_war_data = {
            "state": "inWar",
            "startTime": "20250105T120000.000Z",
            "endTime": "20250106T120000.000Z",
            "warLeague": {"name": "Crystal League I"},
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {
                        "name": "Player1",
                        "tag": "#ABC123",
                        "mapPosition": 1,
                        "attacks": []
                    }
                ]
            }
        }
        
        war = parse_war_data(cwl_war_data)
        self.assertTrue(war.is_cwl, "CWL war not detected (warLeague field present)")


class TestCWLWeekDetection(unittest.TestCase):
    """Test the is_cwl_week() function"""
    
    @patch('bot.datetime')
    def test_cwl_week_day_1(self, mock_datetime):
        """Day 1 of month should be CWL week"""
        mock_datetime.now.return_value = datetime(2025, 1, 1, tzinfo=timezone.utc)
        from bot import is_cwl_week
        self.assertTrue(is_cwl_week())
    
    @patch('bot.datetime')
    def test_cwl_week_day_5(self, mock_datetime):
        """Day 5 of month should be CWL week"""
        mock_datetime.now.return_value = datetime(2025, 1, 5, tzinfo=timezone.utc)
        from bot import is_cwl_week
        self.assertTrue(is_cwl_week())
    
    @patch('bot.datetime')
    def test_cwl_week_day_9(self, mock_datetime):
        """Day 9 of month should be CWL week"""
        mock_datetime.now.return_value = datetime(2025, 1, 9, tzinfo=timezone.utc)
        from bot import is_cwl_week
        self.assertTrue(is_cwl_week())
    
    @patch('bot.datetime')
    def test_not_cwl_week_day_10(self, mock_datetime):
        """Day 10 of month should NOT be CWL week"""
        mock_datetime.now.return_value = datetime(2025, 1, 10, tzinfo=timezone.utc)
        from bot import is_cwl_week
        self.assertFalse(is_cwl_week())
    
    @patch('bot.datetime')
    def test_not_cwl_week_day_15(self, mock_datetime):
        """Day 15 of month should NOT be CWL week"""
        mock_datetime.now.return_value = datetime(2025, 1, 15, tzinfo=timezone.utc)
        from bot import is_cwl_week
        self.assertFalse(is_cwl_week())


class TestWarLogic(unittest.TestCase):
    """Test war parsing and attack tracking logic"""
    
    def test_parse_war_with_no_attacks(self):
        """Test parsing war where no one has attacked"""
        war_data = {
            "state": "inWar",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {"name": "Player1", "tag": "#ABC123", "mapPosition": 1, "attacks": []},
                    {"name": "Player2", "tag": "#DEF456", "mapPosition": 2, "attacks": []},
                ]
            }
        }
        
        war = parse_war_data(war_data)
        self.assertEqual(len(war.members), 2)
        
        remaining = members_with_remaining_attacks(war)
        self.assertEqual(len(remaining), 2)
        self.assertEqual(remaining[0].attacks_remaining, 2)
        self.assertEqual(remaining[1].attacks_remaining, 2)
    
    def test_parse_war_with_one_attack(self):
        """Test parsing war where members have used 1 attack"""
        war_data = {
            "state": "inWar",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {
                        "name": "Player1",
                        "tag": "#ABC123",
                        "mapPosition": 1,
                        "attacks": [{"order": 1, "attackerTag": "#ABC123"}]
                    },
                    {"name": "Player2", "tag": "#DEF456", "mapPosition": 2, "attacks": []},
                ]
            }
        }
        
        war = parse_war_data(war_data)
        remaining = members_with_remaining_attacks(war)
        
        self.assertEqual(len(remaining), 2)
        self.assertEqual(remaining[0].attacks_remaining, 1)  # Player1 has 1 left
        self.assertEqual(remaining[1].attacks_remaining, 2)  # Player2 has 2 left
    
    def test_parse_war_all_attacks_used(self):
        """Test parsing war where everyone used all attacks"""
        war_data = {
            "state": "inWar",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {
                        "name": "Player1",
                        "tag": "#ABC123",
                        "mapPosition": 1,
                        "attacks": [
                            {"order": 1, "attackerTag": "#ABC123"},
                            {"order": 2, "attackerTag": "#ABC123"}
                        ]
                    },
                    {
                        "name": "Player2",
                        "tag": "#DEF456",
                        "mapPosition": 2,
                        "attacks": [
                            {"order": 1, "attackerTag": "#DEF456"},
                            {"order": 2, "attackerTag": "#DEF456"}
                        ]
                    },
                ]
            }
        }
        
        war = parse_war_data(war_data)
        remaining = members_with_remaining_attacks(war)
        
        self.assertEqual(len(remaining), 0, "Should be no members with remaining attacks")
    
    def test_war_not_in_war_state(self):
        """Test that preparation state returns no remaining attacks"""
        war_data = {
            "state": "preparation",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {"name": "Player1", "tag": "#ABC123", "mapPosition": 1, "attacks": []},
                ]
            }
        }
        
        war = parse_war_data(war_data)
        remaining = members_with_remaining_attacks(war)
        
        self.assertEqual(len(remaining), 0, "Preparation state should return 0 remaining attacks")
    
    def test_war_ended_state(self):
        """Test that warEnded state returns no remaining attacks"""
        war_data = {
            "state": "warEnded",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {"name": "Player1", "tag": "#ABC123", "mapPosition": 1, "attacks": []},
                ]
            }
        }
        
        war = parse_war_data(war_data)
        remaining = members_with_remaining_attacks(war)
        
        self.assertEqual(len(remaining), 0, "War ended state should return 0 remaining attacks")
    
    def test_map_position_sorting(self):
        """Test that members are properly sorted by map position"""
        war_data = {
            "state": "inWar",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {"name": "Player5", "tag": "#GHI789", "mapPosition": 5, "attacks": []},
                    {"name": "Player1", "tag": "#ABC123", "mapPosition": 1, "attacks": []},
                    {"name": "Player3", "tag": "#DEF456", "mapPosition": 3, "attacks": []},
                ]
            }
        }
        
        war = parse_war_data(war_data)
        remaining = members_with_remaining_attacks(war)
        remaining.sort(key=lambda m: m.map_position)
        
        self.assertEqual(remaining[0].map_position, 1)
        self.assertEqual(remaining[1].map_position, 3)
        self.assertEqual(remaining[2].map_position, 5)


class TestMemberMapping(unittest.TestCase):
    """Test member mapping functionality"""
    
    def setUp(self):
        """Create a temporary mapping file for testing"""
        self.test_mapping_file = "test_member_mappings.json"
        if os.path.exists(self.test_mapping_file):
            os.remove(self.test_mapping_file)
        self.mapper = MemberMapper(self.test_mapping_file)
    
    def tearDown(self):
        """Clean up test mapping file"""
        if os.path.exists(self.test_mapping_file):
            os.remove(self.test_mapping_file)
    
    def test_add_mapping(self):
        """Test adding a new mapping"""
        self.mapper.add_mapping("#ABC123", 123456789)
        self.assertEqual(self.mapper.get_discord_id("#ABC123"), 123456789)
    
    def test_add_mapping_without_hash(self):
        """Test adding mapping without # prefix (should auto-add)"""
        self.mapper.add_mapping("ABC123", 123456789)
        self.assertEqual(self.mapper.get_discord_id("#ABC123"), 123456789)
    
    def test_remove_mapping(self):
        """Test removing a mapping"""
        self.mapper.add_mapping("#ABC123", 123456789)
        result = self.mapper.remove_mapping("#ABC123")
        
        self.assertTrue(result)
        self.assertIsNone(self.mapper.get_discord_id("#ABC123"))
    
    def test_remove_nonexistent_mapping(self):
        """Test removing a mapping that doesn't exist"""
        result = self.mapper.remove_mapping("#NOTFOUND")
        self.assertFalse(result)
    
    def test_is_mapped(self):
        """Test checking if a tag is mapped"""
        self.mapper.add_mapping("#ABC123", 123456789)
        
        self.assertTrue(self.mapper.is_mapped("#ABC123"))
        self.assertFalse(self.mapper.is_mapped("#NOTFOUND"))
    
    def test_get_all_mappings(self):
        """Test retrieving all mappings"""
        self.mapper.add_mapping("#ABC123", 123456789)
        self.mapper.add_mapping("#DEF456", 987654321)
        
        mappings = self.mapper.get_all_mappings()
        self.assertEqual(len(mappings), 2)
        self.assertIn("#ABC123", mappings)
        self.assertIn("#DEF456", mappings)
    
    def test_persistence(self):
        """Test that mappings persist across instances"""
        self.mapper.add_mapping("#ABC123", 123456789)
        
        # Create new instance with same file
        new_mapper = MemberMapper(self.test_mapping_file)
        self.assertEqual(new_mapper.get_discord_id("#ABC123"), 123456789)
    
    def test_overwrite_mapping(self):
        """Test overwriting an existing mapping"""
        self.mapper.add_mapping("#ABC123", 123456789)
        self.mapper.add_mapping("#ABC123", 999999999)
        
        self.assertEqual(self.mapper.get_discord_id("#ABC123"), 999999999)


class TestTimeCalculations(unittest.TestCase):
    """Test time remaining calculations"""
    
    def test_time_remaining_hours(self):
        """Test calculating hours remaining in war"""
        now = datetime(2025, 1, 24, 10, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 1, 24, 15, 30, 0, tzinfo=timezone.utc)
        
        time_delta = end_time - now
        hours = int(time_delta.total_seconds() // 3600)
        minutes = int((time_delta.total_seconds() % 3600) // 60)
        
        self.assertEqual(hours, 5)
        self.assertEqual(minutes, 30)
    
    def test_time_remaining_minutes_only(self):
        """Test calculating when less than 1 hour remains"""
        now = datetime(2025, 1, 24, 14, 30, 0, tzinfo=timezone.utc)
        end_time = datetime(2025, 1, 24, 15, 15, 0, tzinfo=timezone.utc)
        
        time_delta = end_time - now
        hours = int(time_delta.total_seconds() // 3600)
        minutes = int((time_delta.total_seconds() % 3600) // 60)
        
        self.assertEqual(hours, 0)
        self.assertEqual(minutes, 45)
    
    def test_war_end_time_parsing(self):
        """Test parsing CoC API time format"""
        end_time_str = "20250124T153000.000Z"
        
        # Simulate parsing logic from bot
        end_time_str = end_time_str.replace('Z', '+00:00')
        end_time = datetime.fromisoformat(end_time_str.replace('.000', ''))
        
        expected = datetime(2025, 1, 24, 15, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(end_time, expected)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""
    
    def test_empty_war_roster(self):
        """Test handling war with no members (shouldn't happen but let's be safe)"""
        war_data = {
            "state": "inWar",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": []
            }
        }
        
        war = parse_war_data(war_data)
        self.assertEqual(len(war.members), 0)
        
        remaining = members_with_remaining_attacks(war)
        self.assertEqual(len(remaining), 0)
    
    def test_large_war_roster(self):
        """Test handling 50v50 war (maximum size)"""
        members = []
        for i in range(1, 51):
            members.append({
                "name": f"Player{i}",
                "tag": f"#TAG{i:03d}",
                "mapPosition": i,
                "attacks": []
            })
        
        war_data = {
            "state": "inWar",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {"members": members}
        }
        
        war = parse_war_data(war_data)
        self.assertEqual(len(war.members), 50)
        
        remaining = members_with_remaining_attacks(war)
        self.assertEqual(len(remaining), 50)
    
    def test_mixed_attack_states(self):
        """Test war with members in various attack states"""
        war_data = {
            "state": "inWar",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {"name": "NoAttacks", "tag": "#TAG001", "mapPosition": 1, "attacks": []},
                    {
                        "name": "OneAttack",
                        "tag": "#TAG002",
                        "mapPosition": 2,
                        "attacks": [{"order": 1}]
                    },
                    {
                        "name": "TwoAttacks",
                        "tag": "#TAG003",
                        "mapPosition": 3,
                        "attacks": [{"order": 1}, {"order": 2}]
                    },
                ]
            }
        }
        
        war = parse_war_data(war_data)
        remaining = members_with_remaining_attacks(war)
        
        # Only NoAttacks and OneAttack should be in remaining
        self.assertEqual(len(remaining), 2)
        self.assertEqual(remaining[0].attacks_remaining, 2)  # NoAttacks
        self.assertEqual(remaining[1].attacks_remaining, 1)  # OneAttack
    
    def test_special_characters_in_names(self):
        """Test handling names with special characters"""
        war_data = {
            "state": "inWar",
            "startTime": "20250122T120000.000Z",
            "endTime": "20250124T120000.000Z",
            "isWarLogPublic": True,
            "clan": {
                "members": [
                    {"name": "Player™", "tag": "#ABC123", "mapPosition": 1, "attacks": []},
                    {"name": "Player|Elite", "tag": "#DEF456", "mapPosition": 2, "attacks": []},
                    {"name": "🔥Player🔥", "tag": "#GHI789", "mapPosition": 3, "attacks": []},
                ]
            }
        }
        
        war = parse_war_data(war_data)
        self.assertEqual(len(war.members), 3)
        self.assertEqual(war.members[0].name, "Player™")
        self.assertEqual(war.members[1].name, "Player|Elite")
        self.assertEqual(war.members[2].name, "🔥Player🔥")


class TestRateLimiting(unittest.IsolatedAsyncioTestCase):
    """Test rate limiting functionality"""
    
    async def test_rate_limit_allows_first_command(self):
        """First command should always be allowed"""
        from bot import check_rate_limit, user_cooldowns
        
        # Clear any existing cooldowns
        user_cooldowns.clear()
        
        # Mock context
        ctx = Mock()
        ctx.author.id = 12345
        ctx.send = Mock(return_value=asyncio.Future())
        ctx.send.return_value.set_result(None)
        
        result = await check_rate_limit(ctx)
        self.assertTrue(result, "First command should be allowed")
    
    async def test_rate_limit_blocks_rapid_commands(self):
        """Rapid commands should be blocked"""
        from bot import check_rate_limit, user_cooldowns, COMMAND_COOLDOWN_SECONDS
        
        user_cooldowns.clear()
        
        ctx = Mock()
        ctx.author.id = 12345
        ctx.send = Mock(return_value=asyncio.Future())
        ctx.send.return_value.set_result(None)
        
        # First command
        result1 = await check_rate_limit(ctx)
        self.assertTrue(result1)
        
        # Immediate second command (should be blocked)
        result2 = await check_rate_limit(ctx)
        self.assertFalse(result2, "Rapid second command should be blocked")
    
    async def test_rate_limit_allows_after_cooldown(self):
        """Commands should be allowed after cooldown expires"""
        from bot import check_rate_limit, user_cooldowns, COMMAND_COOLDOWN_SECONDS
        
        user_cooldowns.clear()
        
        ctx = Mock()
        ctx.author.id = 12345
        ctx.send = Mock(return_value=asyncio.Future())
        ctx.send.return_value.set_result(None)
        
        # First command
        result1 = await check_rate_limit(ctx)
        self.assertTrue(result1)
        
        # Wait for cooldown
        await asyncio.sleep(COMMAND_COOLDOWN_SECONDS + 0.1)
        
        # Second command (should be allowed)
        result2 = await check_rate_limit(ctx)
        self.assertTrue(result2, "Command after cooldown should be allowed")
    
    async def test_rate_limit_different_users(self):
        """Different users should have independent rate limits"""
        from bot import check_rate_limit, user_cooldowns
        
        user_cooldowns.clear()
        
        ctx1 = Mock()
        ctx1.author.id = 11111
        ctx1.send = Mock(return_value=asyncio.Future())
        ctx1.send.return_value.set_result(None)
        
        ctx2 = Mock()
        ctx2.author.id = 22222
        ctx2.send = Mock(return_value=asyncio.Future())
        ctx2.send.return_value.set_result(None)
        
        # User 1 command
        result1 = await check_rate_limit(ctx1)
        self.assertTrue(result1)
        
        # User 2 command (should still be allowed)
        result2 = await check_rate_limit(ctx2)
        self.assertTrue(result2, "Different users should have independent rate limits")


def run_tests():
    """Run all tests and print results"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestCWLDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestCWLWeekDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestWarLogic))
    suite.addTests(loader.loadTestsFromTestCase(TestMemberMapping))
    suite.addTests(loader.loadTestsFromTestCase(TestTimeCalculations))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimiting))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED! Bot is ready for 24/7 deployment.")
    else:
        print("\n❌ SOME TESTS FAILED! Review failures before deployment.")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)