import unittest
from unittest.mock import patch, mock_open
import datetime
import os
import csv

# Import the module under test
import stats

class TestStats(unittest.TestCase):

    def test_get_next_word(self):
        self.assertEqual(stats.get_next_word("Team: BLEED", "Team:"), "BLEED")
        self.assertEqual(stats.get_next_word("Entering Normal fight", "Entering"), "Normal")
        self.assertEqual(stats.get_next_word("no search word", "missing"), None)
        self.assertEqual(stats.get_next_word("last word is", "is"), None)
        self.assertEqual(stats.get_next_word("", "anything"), None)

    def test_unix_time(self):
        # We need to compute expected time using datetime to handle timezone differences of the running system.
        # stats.unix_time calls datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").timestamp()
        dt_str = "2026-05-17 15:54:15"
        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        expected_ts = int(dt.timestamp())
        
        self.assertEqual(stats.unix_time(f"{dt_str},335"), expected_ts)
        self.assertEqual(stats.unix_time(f"{dt_str},335", shift=10), expected_ts - 10)

    def test_format_time(self):
        self.assertEqual(stats.format_time(None), "no data")
        self.assertEqual(stats.format_time(0), "00:00")
        self.assertEqual(stats.format_time(59), "00:59")
        self.assertEqual(stats.format_time(60), "01:00")
        self.assertEqual(stats.format_time(125), "02:05")
        self.assertEqual(stats.format_time(3605), "60:05")

    def test_process_log_file(self):
        mock_log_content = (
            "2026-05-17 15:54:15,335 - INFO - Team: POISE\n"
            "2026-05-17 15:54:15,335 - INFO - Unrelated line\n"
            "2026-05-17 15:54:15,335 - INFO - Entering Normal fight\n"
        )
        with patch("builtins.open", mock_open(read_data=mock_log_content)):
            lines = stats.process_log_file("dummy_path.log")
            self.assertEqual(len(lines), 2)
            self.assertIn("Team: POISE", lines[0])
            self.assertIn("Entering Normal fight", lines[1])

    def test_build_data_and_run_parsing(self):
        log_lines = [
            "2026-05-17 15:00:00,000 - INFO - Team: POISE",
            "2026-05-17 15:00:01,000 - INFO - Difficulty: NORMAL",
            "2026-05-17 15:00:02,000 - INFO - Floor 1",
            "2026-05-17 15:00:03,000 - INFO - Pack: TheOutcast",
            "2026-05-17 15:00:05,000 - INFO - Entering Normal fight",
            "2026-05-17 15:00:15,000 - INFO - Battle is over",
            "2026-05-17 15:00:20,000 - INFO - Floor 2",
            "2026-05-17 15:00:21,000 - INFO - Pack: NestWorkshopandTechnology",
            "2026-05-17 15:00:25,000 - INFO - Entering Boss fight",
            "2026-05-17 15:00:35,000 - INFO - Battle is over",
            "2026-05-17 15:00:40,000 - INFO - Floor 3",
            "2026-05-17 15:00:45,000 - INFO - Floor 4",
            "2026-05-17 15:00:50,000 - INFO - Floor 5",
            # Pause / Resume simulation
            "2026-05-17 15:00:55,000 - INFO - Execution paused",
            "2026-05-17 15:01:05,000 - INFO - Execution resumed",
            "2026-05-17 15:01:15,000 - INFO - Run Completed"
        ]
        
        data = stats.build_data(log_lines)
        self.assertEqual(len(data), 1)
        run = data[0]
        self.assertEqual(run.team, "POISE")
        self.assertEqual(run.diff, "NORMAL")
        self.assertEqual(run.state, 5)
        # Total time: 75 seconds duration minus 10 seconds paused shift = 65 seconds
        self.assertEqual(run.time, 65)
        
        # Check Floor 1 details
        self.assertIn(1, run.floors)
        floor1 = run.floors[1]
        self.assertEqual(floor1.pack, "TheOutcast")
        # Floor 1 starts at 15:00:02 and ends when Floor 2 starts at 15:00:20 (18 seconds)
        self.assertEqual(floor1.time, 18)
        # Check normal battle duration (15:00:15 - 15:00:05 = 10 seconds)
        self.assertEqual(floor1.battles["Normal"], [10])

        # Check Floor 2 details
        self.assertIn(2, run.floors)
        floor2 = run.floors[2]
        self.assertEqual(floor2.pack, "NestWorkshopandTechnology")
        # Floor 2 starts at 15:00:20 and ends at Floor 3 starts at 15:00:40 (20 seconds)
        self.assertEqual(floor2.time, 20)
        # Check Boss battle duration (15:00:35 - 15:00:25 = 10 seconds)
        self.assertEqual(floor2.battles["Boss"], [10])

    def test_export_to_csv(self):
        # Create a mock run
        run = stats.Run(st_time=1000, team="POISE")
        run.add_diff("NORMAL")
        run.add_floor(1, st_time=1001)
        run.add_pack("TheOutcast")
        run.add_event(st_time=1002, event="Normal")
        run.end_event(end_time=1005) # 3 seconds
        run.floors[1].end(end_time=1010) # 9 seconds
        run.end(end_time=1020) # 20 seconds
        
        data = [run]
        test_filename = "test_game_output.csv"
        try:
            stats.export_to_csv(data, test_filename)
            self.assertTrue(os.path.exists(test_filename))
            
            # Read CSV content
            with open(test_filename, "r") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
            # Verify basic structure
            self.assertEqual(rows[0], ["NORMAL"])
            # Find POISE section
            poise_found = False
            for r in rows:
                if r == ["POISE"]:
                    poise_found = True
                    break
            self.assertTrue(poise_found)
            
        finally:
            if os.path.exists(test_filename):
                os.remove(test_filename)

if __name__ == "__main__":
    unittest.main()
