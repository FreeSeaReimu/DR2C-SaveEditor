"""不触碰真实游戏存档的核心回归测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dr2c_core import (
    assert_same_gstats_structure, backup_and_replace, convert_bytes, gstats_filename,
    patch_activity, read_activity, read_gstats, replace_trunk_weapons,
    set_gstats_fields, slot_filename,
)


SAMPLE = (
    b'"Falcom" 1 #c .name!\r\n'
    b'2 1 #c .health!\r\n'
    b'"Car Nut" 1 #c .perk!\r\n'
    b'"Inventive" 1 #c .trait!\r\n'
    b'6 4 1 #c .stat!\r\n'
    b'1 4 1 #c .knownstat!\r\n'
    b'0 4 1 #c .bonus!\r\n'
    b'10 1 #c .weapona!\r\n'
    b'0 1 #c .weaponb!\r\n'
    b'8 1 trunk.loot!\r\n'
    b'2 103 trunk.weapon!\r\n'
    b"8 ' car-chassis <to\r\n"
    b"8 ' car-max-chassis <to\r\n"
    b"15 ' car-engine <to\r\n"
    b"15 ' car-max-engine <to\r\n"
    b"1 road{ ' road-trip-days } <to\r\n"
    b"15 road{ ' nearcanada-day } <to\r\n"
    b': raw-control \xf4\xf0 ;\r\n'
)


class CoreTests(unittest.TestCase):
    def test_binary_conversion_preserves_raw_control_bytes(self) -> None:
        chinese, report = convert_bytes(SAMPLE, "en_to_zh", activity=True)
        self.assertIn('"车迷"'.encode(), chinese)
        self.assertIn('"创新思维"'.encode(), chinese)
        self.assertIn(b"11 1 #c .weapona!", chinese)
        self.assertIn(b"2 104 trunk.weapon!", chinese)
        self.assertIn(b": raw-control \xf4\xf0 ;", chinese)
        self.assertEqual(report.changed, 4)
        restored, _ = convert_bytes(chinese, "zh_to_en", activity=True)
        self.assertEqual(restored, SAMPLE)

    def test_read_and_patch_known_fields_only(self) -> None:
        model = read_activity(SAMPLE)
        self.assertEqual(model.remaining_days, 15)
        self.assertEqual(model.characters[1].stats[4]["stat"], 6)
        patched = patch_activity(SAMPLE, {
            ("resource", 1, None): 50,
            ("stat", 1, 4): 5,
            ("bonus", 1, 4): 2,
            ("road", 0, "road-trip-days"): 6,
            ("vehicle", 0, "car-engine"): 12.5,
        })
        self.assertIn(b"50 1 trunk.loot!", patched)
        self.assertIn(b"5 4 1 #c .stat!", patched)
        self.assertIn(b"2 4 1 #c .bonus!", patched)
        self.assertIn(b"6 road{ ' road-trip-days } <to", patched)
        self.assertIn(b"12.5 ' car-engine <to", patched)
        self.assertIn(b"\xf4\xf0", patched)

    def test_backup_and_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "0.save"
            target.write_bytes(b"old")
            backup = backup_and_replace(target, b"new", backup_dir=root / "backups")
            self.assertIsNotNone(backup)
            self.assertEqual(backup.read_bytes(), b"old")  # type: ignore[union-attr]
            self.assertEqual(target.read_bytes(), b"new")

    def test_replace_trunk_weapons_preserves_binary_tail(self) -> None:
        replaced = replace_trunk_weapons(SAMPLE, [(11, 3), (249, 10)])
        self.assertIn(b"3 11 trunk.weapon!", replaced)
        self.assertIn(b"10 249 trunk.weapon!", replaced)
        self.assertNotIn(b"2 103 trunk.weapon!", replaced)
        self.assertIn(b": raw-control \xf4\xf0 ;", replaced)

    def test_activity_slot_names_follow_save_language(self) -> None:
        self.assertEqual(slot_filename(0, False), "0.slot")
        self.assertEqual(slot_filename(2, True), "2mod.slot")

    def test_gstats_copy_validation_and_unlocks(self) -> None:
        source = (
            b"0 gstats{ ' wins-normal } <to\n"
            b"7 gstats{ ' wins-normal-streak } <to\n"
            b"1 gstats{ ' perk-mechanic } <to\n"
            b"2 gstats{ ' trait-specialist } <to\n"
        )
        target = (
            b"4 gstats{ ' wins-normal } <to\n"
            b"9 gstats{ ' wins-normal-streak } <to\n"
            b"3 gstats{ ' perk-mechanic } <to\n"
            b"0 gstats{ ' trait-specialist } <to\n"
        )
        assert_same_gstats_structure(source, target)
        modes, count = set_gstats_fields(source, prefixes=("wins-",), value=1)
        self.assertEqual(count, 2)
        self.assertEqual(read_gstats(modes)["wins-normal-streak"], 1)
        unlocks, count = set_gstats_fields(modes, prefixes=("perk-", "trait-"), value=3)
        self.assertEqual(count, 2)
        self.assertEqual(read_gstats(unlocks)["perk-mechanic"], 3)
        self.assertEqual(read_gstats(unlocks)["trait-specialist"], 3)
        self.assertEqual(gstats_filename(False), "gstats.save")
        self.assertEqual(gstats_filename(True), "gstats-mod.save")


if __name__ == "__main__":
    unittest.main(verbosity=2)
