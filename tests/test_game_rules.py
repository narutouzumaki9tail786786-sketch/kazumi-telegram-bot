import unittest

from kazumi.game_rules import (
    BANK_INTEREST_COOLDOWN_SECONDS,
    FARM_GAME_DAILY_CAP,
    MAX_BANK_BALANCE,
    MAX_INVEST_BUY_AMOUNT,
    bank_interest_payout,
    capped_daily_payout,
    dice_duel_result,
    highlow_profile,
    leaderboard_eligible,
    memory_match_multiplier,
    mines_multiplier,
    resolve_target_source,
    safe_invest_sell_value,
    safe_market_price,
    safe_turn_index,
    validate_bet,
    validate_mines_count,
)


class TargetResolutionTests(unittest.TestCase):
    def test_reply_and_explicit_target_is_rejected(self):
        self.assertEqual(resolve_target_source(has_reply=True, explicit_target="@alice"), "conflict")

    def test_reply_is_used_when_no_explicit_target_exists(self):
        self.assertEqual(resolve_target_source(has_reply=True, explicit_target=None), "reply")


class BetValidationTests(unittest.TestCase):
    def test_wordgame_rejects_zero_negative_and_oversized_bets(self):
        self.assertIsNotNone(validate_bet(0, balance=500_000, minimum=100, maximum=25_000))
        self.assertIsNotNone(validate_bet(-500, balance=500_000, minimum=100, maximum=25_000))
        self.assertIsNotNone(validate_bet(25_001, balance=500_000, minimum=100, maximum=25_000))

    def test_wordgame_accepts_the_configured_range(self):
        self.assertIsNone(validate_bet(100, balance=100, minimum=100, maximum=25_000))
        self.assertIsNone(validate_bet(25_000, balance=25_000, minimum=100, maximum=25_000))

    def test_farm_game_daily_payout_is_capped(self):
        self.assertEqual(FARM_GAME_DAILY_CAP, 50_000)
        self.assertEqual(capped_daily_payout(10_000, 0), 10_000)
        self.assertEqual(capped_daily_payout(10_000, 45_000), 5_000)
        self.assertEqual(capped_daily_payout(10_000, 50_000), 0)


class LeaderboardTests(unittest.TestCase):
    def test_only_real_positive_id_users_are_eligible(self):
        self.assertTrue(leaderboard_eligible({"user_id": 123, "is_bot": False, "name": "Nagi"}))
        self.assertFalse(leaderboard_eligible({"user_id": 1087968824, "is_bot": True, "name": "Group Anonymous"}))
        self.assertFalse(leaderboard_eligible({"user_id": 1087968824, "name": "Group Anonymous"}))
        self.assertFalse(leaderboard_eligible({"user_id": -100123, "is_bot": False, "name": "Channel"}))
        self.assertFalse(leaderboard_eligible({"user_id": 456, "is_bot": False, "leaderboard_hidden": True}))


class HighLowTests(unittest.TestCase):
    def test_level_tiers_increase_rounds_and_top_reward(self):
        newbie = highlow_profile(0)
        rookie = highlow_profile(5)
        pro = highlow_profile(15)
        veteran = highlow_profile(30)

        self.assertEqual(newbie["max_rounds"], 3)
        self.assertEqual(rookie["max_rounds"], 4)
        self.assertEqual(pro["max_rounds"], 5)
        self.assertEqual(veteran["max_rounds"], 6)
        self.assertLess(newbie["multipliers"][-1], veteran["multipliers"][-1])


class StatefulGameSafetyTests(unittest.TestCase):
    def test_wordbomb_turn_index_handles_empty_and_shrinking_alive_lists(self):
        self.assertIsNone(safe_turn_index([], 3))
        self.assertEqual(safe_turn_index([10, 20], 3), 1)


class MinesTests(unittest.TestCase):
    def test_mine_count_validation(self):
        self.assertIsNone(validate_mines_count(1))
        self.assertIsNone(validate_mines_count(8))
        self.assertIsNotNone(validate_mines_count(0))
        self.assertIsNotNone(validate_mines_count(9))

    def test_mines_multiplier_grows_after_each_safe_reveal(self):
        first = mines_multiplier(total_cells=25, mines=3, revealed_safe=1)
        second = mines_multiplier(total_cells=25, mines=3, revealed_safe=2)
        third = mines_multiplier(total_cells=25, mines=3, revealed_safe=3)
        self.assertGreater(first, 1.0)
        self.assertGreater(second, first)
        self.assertGreater(third, second)


class MemoryMatchTests(unittest.TestCase):
    def test_multiplier_rewards_fewer_mistakes(self):
        self.assertEqual(memory_match_multiplier(0), 2.0)
        self.assertEqual(memory_match_multiplier(2), 1.6)
        self.assertEqual(memory_match_multiplier(5), 1.25)
        self.assertEqual(memory_match_multiplier(8), 0.0)


class DiceDuelTests(unittest.TestCase):
    def test_dice_result_handles_wins_and_ties(self):
        self.assertEqual(dice_duel_result(6, 2), "p1")
        self.assertEqual(dice_duel_result(1, 4), "p2")
        self.assertEqual(dice_duel_result(3, 3), "tie")


class EconomyGuardTests(unittest.TestCase):
    def test_bank_interest_is_capped_and_not_available_at_max_bank(self):
        self.assertEqual(BANK_INTEREST_COOLDOWN_SECONDS, 48 * 3600)
        self.assertEqual(bank_interest_payout(MAX_BANK_BALANCE), 0)
        self.assertEqual(bank_interest_payout(1_000_000_000), 25_000_000)

    def test_market_price_and_sell_value_are_safeguarded(self):
        self.assertEqual(safe_market_price(0.55, 0.55), 1.0)
        self.assertEqual(safe_market_price(None, 83), 83.0)
        self.assertEqual(safe_invest_sell_value(1_000, 1, 10_000), 3_000)
        self.assertEqual(safe_invest_sell_value(MAX_INVEST_BUY_AMOUNT, 0.25, 999999), MAX_INVEST_BUY_AMOUNT * 3)


if __name__ == "__main__":
    unittest.main()
