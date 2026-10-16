import unittest
from datetime import date

from tiny_recurrence import expand, RRuleError


class TestExpandDaily(unittest.TestCase):

    def test_daily_count(self):
        result = expand("FREQ=DAILY;COUNT=5", date(2025, 6, 1))
        self.assertEqual(
            result,
            [date(2025, 6, 1), date(2025, 6, 2), date(2025, 6, 3),
             date(2025, 6, 4), date(2025, 6, 5)]
        )

    def test_daily_interval(self):
        result = expand("FREQ=DAILY;INTERVAL=2;COUNT=3", date(2025, 6, 1))
        self.assertEqual(result, [date(2025, 6, 1), date(2025, 6, 3), date(2025, 6, 5)])

    def test_daily_until(self):
        result = expand("FREQ=DAILY;UNTIL=20250604", date(2025, 6, 1))
        self.assertEqual(
            result,
            [date(2025, 6, 1), date(2025, 6, 2), date(2025, 6, 3), date(2025, 6, 4)]
        )

    def test_daily_until_excludes_after(self):
        result = expand("FREQ=DAILY;UNTIL=20250603", date(2025, 6, 1))
        self.assertEqual(result, [date(2025, 6, 1), date(2025, 6, 2), date(2025, 6, 3)])


class TestExpandWeekly(unittest.TestCase):

    def test_weekly_no_byday(self):
        result = expand("FREQ=WEEKLY;COUNT=3", date(2025, 6, 2))  # Monday
        self.assertEqual(
            result,
            [date(2025, 6, 2), date(2025, 6, 9), date(2025, 6, 16)]
        )

    def test_weekly_byday_single(self):
        # dtstart is Monday June 2. BYDAY=FR. Anchor week yields Fri June 6.
        result = expand("FREQ=WEEKLY;BYDAY=FR;COUNT=2", date(2025, 6, 2))
        self.assertEqual(result, [date(2025, 6, 6), date(2025, 6, 13)])

    def test_weekly_byday_multiple_same_week(self):
        # dtstart is Monday June 2. BYDAY=MO,WE,FR.
        # Anchor week: Mon 2, Wed 4, Fri 6 (all >= dtstart).
        # Next week: Mon 9, Wed 11, Fri 13.
        result = expand("FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=6", date(2025, 6, 2))
        self.assertEqual(
            result,
            [date(2025, 6, 2), date(2025, 6, 4), date(2025, 6, 6),
             date(2025, 6, 9), date(2025, 6, 11), date(2025, 6, 13)]
        )

    def test_weekly_byday_dtstart_not_in_byday(self):
        # dtstart is Tuesday June 3. BYDAY=MO,WE,FR.
        # Anchor week (start Mon Jun 2): Wed 4, Fri 6 (Mon 2 is < dtstart, skipped).
        result = expand("FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=3", date(2025, 6, 3))
        self.assertEqual(result, [date(2025, 6, 4), date(2025, 6, 6), date(2025, 6, 9)])

    def test_weekly_interval(self):
        # dtstart is Mon June 2. BYDAY=MO,FR. INTERVAL=2.
        # Week 0: Mon 2, Fri 6. Week 2: Mon 16, Fri 20.
        result = expand("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,FR;COUNT=4", date(2025, 6, 2))
        self.assertEqual(
            result,
            [date(2025, 6, 2), date(2025, 6, 6), date(2025, 6, 16), date(2025, 6, 20)]
        )


class TestExpandMonthly(unittest.TestCase):

    def test_monthly_no_bymonthday(self):
        result = expand("FREQ=MONTHLY;COUNT=3", date(2025, 1, 15))
        self.assertEqual(result, [date(2025, 1, 15), date(2025, 2, 15), date(2025, 3, 15)])

    def test_monthly_interval(self):
        result = expand("FREQ=MONTHLY;INTERVAL=2;COUNT=3", date(2025, 1, 15))
        self.assertEqual(result, [date(2025, 1, 15), date(2025, 3, 15), date(2025, 5, 15)])

    def test_monthly_day31_skips_february(self):
        # BYMONTHDAY=31: Jan 31, Feb skipped, Mar 31.
        result = expand("FREQ=MONTHLY;BYMONTHDAY=31;COUNT=2", date(2025, 1, 31))
        self.assertEqual(result, [date(2025, 1, 31), date(2025, 3, 31)])

    def test_monthly_day31_across_year_boundary(self):
        # Oct 31, Nov skipped, Dec 31, Jan 31, Feb skipped, Mar 31.
        result = expand("FREQ=MONTHLY;BYMONTHDAY=31;COUNT=3", date(2024, 10, 31))
        self.assertEqual(result, [date(2024, 10, 31), date(2024, 12, 31), date(2025, 1, 31)])

    def test_monthly_bymonthday_multiple(self):
        # BYMONTHDAY=1,15. January yields 1, 15. Feb yields 1, 15.
        result = expand("FREQ=MONTHLY;BYMONTHDAY=1,15;COUNT=4", date(2025, 1, 1))
        self.assertEqual(result, [date(2025, 1, 1), date(2025, 1, 15),
                                   date(2025, 2, 1), date(2025, 2, 15)])

    def test_monthly_until(self):
        result = expand("FREQ=MONTHLY;BYMONTHDAY=1;UNTIL=20250301", date(2025, 1, 1))
        self.assertEqual(result, [date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1)])


class TestParsing(unittest.TestCase):

    def test_rrule_prefix_stripped(self):
        result = expand("RRULE:FREQ=DAILY;COUNT=2", date(2025, 6, 1))
        self.assertEqual(result, [date(2025, 6, 1), date(2025, 6, 2)])

    def test_missing_freq_raises(self):
        with self.assertRaises(RRuleError):
            expand("INTERVAL=1;COUNT=3", date(2025, 6, 1))

    def test_unsupported_freq_raises(self):
        with self.assertRaises(RRuleError):
            expand("FREQ=YEARLY;COUNT=1", date(2025, 6, 1))

    def test_invalid_interval_raises(self):
        with self.assertRaises(RRuleError):
            expand("FREQ=DAILY;INTERVAL=0;COUNT=1", date(2025, 6, 1))

    def test_until_datetime_raises(self):
        with self.assertRaises(RRuleError):
            expand("FREQ=DAILY;UNTIL=20250601T000000Z", date(2025, 6, 1))

    def test_byday_wrong_freq_raises(self):
        with self.assertRaises(RRuleError):
            expand("FREQ=DAILY;BYDAY=MO;COUNT=1", date(2025, 6, 1))

    def test_bymonthday_wrong_freq_raises(self):
        with self.assertRaises(RRuleError):
            expand("FREQ=DAILY;BYMONTHDAY=15;COUNT=1", date(2025, 6, 1))

    def test_invalid_byday_raises(self):
        with self.assertRaises(RRuleError):
            expand("FREQ=WEEKLY;BYDAY=XX;COUNT=1", date(2025, 6, 1))

    def test_negative_bymonthday_raises(self):
        with self.assertRaises(RRuleError):
            expand("FREQ=MONTHLY;BYMONTHDAY=-1;COUNT=1", date(2025, 1, 31))

    def test_empty_rule_raises(self):
        with self.assertRaises(RRuleError):
            expand("", date(2025, 6, 1))


class TestLimit(unittest.TestCase):

    def test_limit_truncates_open_ended(self):
        result = expand("FREQ=DAILY", date(2025, 6, 1), limit=3)
        self.assertEqual(result, [date(2025, 6, 1), date(2025, 6, 2), date(2025, 6, 3)])

    def test_count_smaller_than_limit(self):
        result = expand("FREQ=DAILY;COUNT=2", date(2025, 6, 1), limit=100)
        self.assertEqual(result, [date(2025, 6, 1), date(2025, 6, 2)])

    def test_limit_smaller_than_count(self):
        result = expand("FREQ=DAILY;COUNT=10", date(2025, 6, 1), limit=2)
        self.assertEqual(result, [date(2025, 6, 1), date(2025, 6, 2)])

    def test_limit_too_small_raises(self):
        with self.assertRaises(RRuleError):
            expand("FREQ=DAILY;COUNT=5", date(2025, 6, 1), limit=0)


if __name__ == "__main__":
    unittest.main()
