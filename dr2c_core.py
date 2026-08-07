"""DR2C 存档的二进制安全读取、转换与定点编辑。

活动存档中混有 Deathforth 的原始控制字节，因此此模块永远不会对整份
活动存档做 decode()/encode()。所有修改都只替换已识别字段所在的一行。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
BACKUP_DIR = APP_DIR / "backups"
DEFAULT_SAVE_DIR = Path(os.environ.get("APPDATA", "")) / ".madgarden" / "DR2C"

STAT_NAMES = {
    0: "morale", 1: "attitude", 2: "composure", 3: "charm", 4: "wits",
    5: "loyalty", 6: "medical", 7: "mechanical", 8: "shooting",
    9: "strength", 10: "dexterity", 11: "fitness", 12: "vitality",
}
STAT_LABELS = {
    "morale": "士气", "attitude": "态度", "composure": "镇定", "charm": "魅力",
    "wits": "机智", "loyalty": "忠诚", "medical": "医疗", "mechanical": "机械",
    "shooting": "射击", "strength": "力量", "dexterity": "灵巧", "fitness": "体能",
    "vitality": "生命上限",
}
RESOURCE_LABELS = {1: "食物", 2: "汽油", 3: "医疗物资", 4: "手枪弹", 5: "步枪弹", 6: "霰弹"}

_TEXT_FIELD = re.compile(rb'^"(?P<value>[^\"]*)"\s+(?P<char>\d+)\s+#c\s+\.(?P<field>name|perk|trait)!\s*$')
_STAT_FIELD = re.compile(rb'^(?P<value>-?\d+)\s+(?P<stat>\d+)\s+(?P<char>\d+)\s+#c\s+\.(?P<field>stat|bonus|knownstat)!\s*$')
_HP_FIELD = re.compile(rb'^(?P<value>-?\d+)\s+(?P<char>\d+)\s+#c\s+\.health!\s*$')
_HAND_FIELD = re.compile(rb'^(?P<value>\d+)\s+(?P<char>\d+)\s+#c\s+\.(?P<field>weapona|weaponb|weaponc)!\s*$')
_LOOT_FIELD = re.compile(rb'^(?P<value>-?\d+)\s+(?P<id>\d+)\s+trunk\.loot!\s*$')
_TRUNK_WEAPON = re.compile(rb'^(?P<value>-?\d+)\s+(?P<id>\d+)\s+trunk\.weapon!\s*$')
_CAR_FIELD = re.compile(rb'^(?P<value>-?\d+(?:\.\d+)?)\s+\'\s+(?P<field>car-(?:max-)?(?:chassis|engine|armor|speed)|car-mpg|car-repair)\s+<to\s*$')
_ROAD_FIELD = re.compile(rb'^(?P<value>-?\d+)\s+road\{\s+\'\s+(?P<field>road-trip-days|nearcanada-day)\s+}\s+<to\s*$')
_GSTAT_FIELD = re.compile(rb"^(?P<value>-?\d+)\s+gstats\{\s+'\s+(?P<field>[A-Za-z0-9+_-]+)\s+}\s+<to\s*$")
_GSTAT_ASSIGNMENT = re.compile(rb"^.*?gstats\{\s+'\s+(?P<field>[A-Za-z0-9+_-]+)\s+}\s+<to\s*$")
_STACK_TARGET = re.compile(
    rb"(?:[A-Za-z0-9_-]+\{\s+)?'\s+(?P<field>[A-Za-z0-9_-]+)\s+(?:}\s+)?<to\s*$"
)

# 这些字段保存的是已经洗过牌的地区／随机事件堆。堆中的部分 Forth 词标识和
# 富文本内容随语言包本地化，不能直接跨语言 evaluate。载入游戏时目标语言的定义
# 已经先把默认堆创建好，因此跨语言时应保留该默认值、舍弃来源语言的旧堆。
_CROSS_LOCALE_TRANSIENT_STACKS = frozenset({
    # regiondef{
    "rare-lot-deck", "trader-list", "trader-list-rare", "trader-draw-pick",
    "dochead-pick-stack-base", "camprecruit-list", "camprecruit-draw-pick",
    "camprecruit-list-rare", "tnome-reward-1-deck", "tnome-reward-2-deck",
    "tnome-reward-3-deck",
    # road{
    "daily-deck", "fate-deck", "innerraid-deck", "rareinnerraid-deck",
    "specialchar-deck", "normalchar-deck", "specialchargood-deck",
    "specialcharbad-deck", "recruit-deck", "easyinnerraid-deck",
    "easycityraid-deck", "cityraid-deck", "hazardraid-deck",
    "easyhazardraid-deck", "canadahazard-deck", "trade-camp-deck",
    "trade-camp-special-deck", "walk-camp-deck", "find-car-deck", "walk-deck",
    "day-pick-deck", "day-shuffle-deck", "common-deck", "rare-deck", "camp-deck",
    "despair-solo-deck", "despair-dog-deck", "despair-deck", "bandit-deck",
    "trade-deck", "loc-pick-stack", "loc-pick-rare", "clouds-pick-stack",
})


class SaveError(RuntimeError):
    """存档不适合安全处理时抛出。"""


@dataclass
class Character:
    char_id: int
    name: str = ""
    perk: str = ""
    trait: str = ""
    hp: int | None = None
    stats: dict[int, dict[str, int]] = field(default_factory=dict)
    weapons: dict[str, int] = field(default_factory=dict)


@dataclass
class ActivityModel:
    characters: dict[int, Character] = field(default_factory=dict)
    resources: dict[int, int] = field(default_factory=dict)
    trunk_weapons: dict[int, int] = field(default_factory=dict)
    vehicle: dict[str, float] = field(default_factory=dict)
    road_trip_days: int | None = None
    near_canada_day: int | None = None

    @property
    def remaining_days(self) -> int | None:
        if self.road_trip_days is None or self.near_canada_day is None:
            return None
        return self.near_canada_day + 1 - self.road_trip_days


@dataclass(frozen=True)
class ConversionReport:
    changed: int
    perks: int
    traits: int
    weapons: int
    renamed: int
    transient_stacks: int = 0
    unknown: tuple[str, ...] = ()


@dataclass(frozen=True)
class GStatsMergeReport:
    """全局升级存档互转采用的兼容策略及其影响。"""

    mode: str
    copied_fields: int
    zeroed_target_fields: tuple[str, ...] = ()


def load_mapping(path: Path | None = None) -> dict[str, dict[str, str]]:
    path = path or DATA_DIR / "trait_perk_map.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"perk": data["perks"], "trait": data["traits"]}


def reverse_mapping(mapping: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for field, table in mapping.items():
        reversed_table = {translated: source for source, translated in table.items()}
        if len(reversed_table) != len(table):
            raise SaveError(f"{field} 对照表存在重复译名，不能安全反向转换。")
        result[field] = reversed_table
    return result


def save_filename(slot: int, chinese: bool, custom: bool = False) -> str:
    if custom:
        return "custchars-mod.save" if chinese else "custchars.save"
    if slot not in (0, 1, 2):
        raise ValueError("存档槽仅支持 0、1、2。")
    return f"{slot}{'mod' if chinese else ''}.save"


def slot_filename(slot: int, chinese: bool) -> str:
    """活动存档在菜单中显示的摘要文件名；自建角色没有对应 .slot。"""
    if slot not in (0, 1, 2):
        raise ValueError("存档槽仅支持 0、1、2。")
    return f"{slot}{'mod' if chinese else ''}.slot"


def gstats_filename(chinese: bool) -> str:
    return "gstats-mod.save" if chinese else "gstats.save"


def _parts(data: bytes) -> list[tuple[bytes, bytes]]:
    """返回 (正文, 换行符)，保留每一个原始字节。"""
    result = []
    # 不用 bytes.splitlines()：它会把 \v、\f 等二进制控制字节也当成换行，
    # 而 Deathforth 富文本恰好会把原始控制码嵌进存档。
    chunks = data.split(b"\n")
    for index, raw in enumerate(chunks):
        ending = b"\n" if index < len(chunks) - 1 else b""
        if raw.endswith(b"\r"):
            raw = raw[:-1]
            ending = b"\r\n" if ending else b"\r"
        result.append((raw, ending))
    return result


def _join(parts: Iterable[tuple[bytes, bytes]]) -> bytes:
    return b"".join(body + ending for body, ending in parts)


def _decode(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SaveError("待修改字段不是有效 UTF-8，已拒绝写入以保护存档。") from exc


def _encode_text(value: str) -> bytes:
    if '"' in value or "\r" in value or "\n" in value:
        raise SaveError("名字、perk 或 trait 不能含双引号或换行。")
    return value.encode("utf-8")


def read_activity(data: bytes) -> ActivityModel:
    model = ActivityModel()
    for body, _ in _parts(data):
        if match := _TEXT_FIELD.match(body):
            char_id = int(match["char"])
            char = model.characters.setdefault(char_id, Character(char_id))
            setattr(char, match["field"].decode(), _decode(match["value"]))
        elif match := _STAT_FIELD.match(body):
            char_id, stat_id = int(match["char"]), int(match["stat"])
            char = model.characters.setdefault(char_id, Character(char_id))
            char.stats.setdefault(stat_id, {})[match["field"].decode()] = int(match["value"])
        elif match := _HP_FIELD.match(body):
            char_id = int(match["char"])
            model.characters.setdefault(char_id, Character(char_id)).hp = int(match["value"])
        elif match := _HAND_FIELD.match(body):
            char_id = int(match["char"])
            model.characters.setdefault(char_id, Character(char_id)).weapons[match["field"].decode()] = int(match["value"])
        elif match := _LOOT_FIELD.match(body):
            model.resources[int(match["id"])] = int(match["value"])
        elif match := _TRUNK_WEAPON.match(body):
            model.trunk_weapons[int(match["id"])] = int(match["value"])
        elif match := _CAR_FIELD.match(body):
            model.vehicle[match["field"].decode()] = float(match["value"])
        elif match := _ROAD_FIELD.match(body):
            setattr(model, "road_trip_days" if match["field"] == b"road-trip-days" else "near_canada_day", int(match["value"]))
    return model


def _replace_value(body: bytes, match: re.Match[bytes], value: bytes) -> bytes:
    start, end = match.span("value")
    return body[:start] + value + body[end:]


def _reset_cross_locale_transient_stacks(parts: list[tuple[bytes, bytes]]) -> tuple[list[tuple[bytes, bytes]], int]:
    """删除跨语言不兼容的 ``0 stack ... <to`` 保存块。

    只处理游戏启动时会创建默认值的地区／路途牌堆；当前流程 ``road-stack``、
    天数、游戏模式和所有普通数值字段均不会碰。
    """
    output: list[tuple[bytes, bytes]] = []
    reset = 0
    index = 0
    while index < len(parts):
        body, ending = parts[index]
        if body.strip() != b"0 stack":
            output.append((body, ending))
            index += 1
            continue

        target_index: int | None = None
        target_field: bytes | None = None
        for candidate in range(index + 1, len(parts)):
            candidate_body = parts[candidate][0]
            if b"<to" not in candidate_body:
                continue
            match = _STACK_TARGET.search(candidate_body)
            if match:
                target_index = candidate
                target_field = match["field"]
            break

        if target_index is not None and target_field is not None and target_field.decode("ascii") in _CROSS_LOCALE_TRANSIENT_STACKS:
            reset += 1
            index = target_index + 1
            continue

        output.append((body, ending))
        index += 1
    return output, reset


def convert_bytes(data: bytes, direction: str, *, activity: bool) -> tuple[bytes, ConversionReport]:
    """转换 perk/trait 与武器 ID；direction 是 en_to_zh 或 zh_to_en。"""
    if direction not in {"en_to_zh", "zh_to_en"}:
        raise ValueError("direction 必须为 en_to_zh 或 zh_to_en。")
    mapping = load_mapping()
    table = mapping if direction == "en_to_zh" else reverse_mapping(mapping)
    offset = 1 if direction == "en_to_zh" else -1
    parts = _parts(data)
    unknown: set[str] = set()
    text_changes: dict[int, tuple[re.Match[bytes], bytes]] = {}
    chinese_name_ids: set[int] = set()
    perks = traits = weapons = renamed = 0

    for index, (body, _) in enumerate(parts):
        if match := _TEXT_FIELD.match(body):
            field = match["field"].decode()
            value = _decode(match["value"])
            char_id = int(match["char"])
            if field in ("perk", "trait") and value:
                converted = table[field].get(value)
                if converted is None:
                    unknown.add(f"{field}: {value}")
                else:
                    text_changes[index] = (match, _encode_text(converted))
                    perks += field == "perk"
                    traits += field == "trait"
            elif activity and direction == "zh_to_en" and field == "name" and value:
                # 英文版可保留已有 ASCII 名字；只有含中日韩统一表意文字的名字
                # 才改为 A1/A2…，以避免英文版 Forth 字体/解析兼容问题。
                if any("\u4e00" <= character <= "\u9fff" for character in value):
                    chinese_name_ids.add(char_id)

    if unknown:
        details = "；".join(sorted(unknown))
        raise SaveError(f"存在未收录的 perk/trait，已取消转换：{details}")

    name_replacements = {char_id: f"A{position}" for position, char_id in enumerate(sorted(chinese_name_ids), 1)}
    output: list[tuple[bytes, bytes]] = []
    for index, (body, ending) in enumerate(parts):
        if index in text_changes:
            match, value = text_changes[index]
            body = _replace_value(body, match, value)
        elif (match := _TEXT_FIELD.match(body)) and activity and direction == "zh_to_en" and match["field"] == b"name":
            char_id = int(match["char"])
            if char_id in name_replacements:
                body = _replace_value(body, match, _encode_text(name_replacements[char_id]))
                renamed += 1
        elif match := _HAND_FIELD.match(body):
            weapon_id = int(match["value"])
            if weapon_id:
                translated = weapon_id + offset
                if translated < 1:
                    raise SaveError(f"武器 ID {weapon_id} 无法按当前偏移规则反向转换。")
                body = _replace_value(body, match, str(translated).encode())
                weapons += 1
        elif match := _TRUNK_WEAPON.match(body):
            weapon_id = int(match["id"])
            if weapon_id:
                translated = weapon_id + offset
                if translated < 1:
                    raise SaveError(f"后备箱武器 ID {weapon_id} 无法按当前偏移规则反向转换。")
                start, end = match.span("id")
                body = body[:start] + str(translated).encode() + body[end:]
                weapons += 1
        output.append((body, ending))

    transient_stacks = 0
    if activity:
        # 不同语言包会把牌堆中的 Forth 词标识和富文本一同本地化。原样保留会令
        # $load-savefile 在区域状态处中止，导致后面的天数和 gamemode 都没被读到。
        output, transient_stacks = _reset_cross_locale_transient_stacks(output)

    result = _join(output)
    if result.startswith(b"\xef\xbb\xbf"):
        raise SaveError("输出包含 UTF-8 BOM，已拒绝写入。")
    return result, ConversionReport(
        perks + traits + weapons + renamed + transient_stacks,
        perks,
        traits,
        weapons,
        renamed,
        transient_stacks,
    )


def patch_activity(data: bytes, updates: dict[tuple[str, int, int | str | None], int | float | str]) -> bytes:
    """按键值修改活动存档。键形如 ('resource', id, None) 或 ('stat', char, stat)。"""
    parts = _parts(data)
    seen: set[tuple[str, int, int | str | None]] = set()
    output: list[tuple[bytes, bytes]] = []
    for body, ending in parts:
        key: tuple[str, int, int | str | None] | None = None
        match: re.Match[bytes] | None = None
        text = False
        if m := _TEXT_FIELD.match(body):
            key, match, text = (m["field"].decode(), int(m["char"]), None), m, True
        elif m := _STAT_FIELD.match(body):
            key, match = (m["field"].decode(), int(m["char"]), int(m["stat"])), m
        elif m := _HP_FIELD.match(body):
            key, match = ("hp", int(m["char"]), None), m
        elif m := _HAND_FIELD.match(body):
            key, match = (m["field"].decode(), int(m["char"]), None), m
        elif m := _LOOT_FIELD.match(body):
            key, match = ("resource", int(m["id"]), None), m
        elif m := _TRUNK_WEAPON.match(body):
            key, match = ("trunk_weapon", int(m["id"]), None), m
        elif m := _CAR_FIELD.match(body):
            key, match = ("vehicle", 0, m["field"].decode()), m
        elif m := _ROAD_FIELD.match(body):
            key, match = ("road", 0, m["field"].decode()), m
        if key in updates and match is not None:
            value = updates[key]
            if text:
                encoded = _encode_text(str(value))
            elif isinstance(value, float):
                encoded = (f"{value:g}").encode()
            else:
                encoded = str(value).encode()
            body = _replace_value(body, match, encoded)
            seen.add(key)
        output.append((body, ending))
    missing = set(updates) - seen
    if missing:
        raise SaveError(f"找不到待修改字段，已取消写入：{sorted(missing)!r}")
    return _join(output)


def replace_trunk_weapons(data: bytes, items: Iterable[tuple[int, int]]) -> bytes:
    """完整替换后备箱武器列表，保留活动存档的其他每一个原始字节。

    存档加载前会初始化后备箱；这里保留第一条 ``trunk.weapon!`` 的位置，
    以新的 ID/数量清单替换所有旧条目。不能找到该区块时拒绝写入，避免把
    指令塞到未知的 Deathforth 存档位置。
    """
    normalized: list[tuple[int, int]] = []
    seen_ids: set[int] = set()
    for weapon_id, amount in items:
        if weapon_id <= 0:
            raise SaveError("后备箱武器 ID 必须大于 0；空栏 0 不能作为库存武器。")
        if amount < 0:
            raise SaveError("后备箱武器数量或充能不能为负数。")
        if weapon_id in seen_ids:
            raise SaveError(f"后备箱武器 ID {weapon_id} 重复，请合并数量后再保存。")
        seen_ids.add(weapon_id)
        normalized.append((weapon_id, amount))

    output: list[tuple[bytes, bytes]] = []
    inserted = False
    for body, ending in _parts(data):
        if _TRUNK_WEAPON.match(body):
            if not inserted:
                for weapon_id, amount in normalized:
                    output.append((f"{amount} {weapon_id} trunk.weapon!".encode("ascii"), ending or b"\n"))
                inserted = True
            continue
        output.append((body, ending))
    if not inserted:
        raise SaveError("存档中找不到后备箱武器区块，已拒绝写入。")
    return _join(output)


def read_gstats(data: bytes) -> dict[str, int]:
    """读取全局升级存档的数值字段，保留原始文件由调用者继续处理。"""
    result: dict[str, int] = {}
    for body, _ in _parts(data):
        if match := _GSTAT_FIELD.match(body):
            field = match["field"].decode("ascii")
            if field in result:
                raise SaveError(f"全局升级存档字段重复：{field}")
            result[field] = int(match["value"])
    if not result:
        raise SaveError("文件中未找到 gstats 字段，不是可识别的全局升级存档。")
    return result


def _gstats_field_blocks(data: bytes) -> tuple[list[tuple[bytes, bytes]], dict[str, tuple[int, int]]]:
    """定位每个 gstats 字段的完整保存块。

    大多数全局字段是一行数值赋值；成就列表等容器则是 ``0 stack`` 开始、
    ``gstats{ ... } <to`` 结束的多行块。合并旧档时，容器字段也必须整体迁移，
    不能只处理数值字段。
    """
    parts = _parts(data)
    blocks: dict[str, tuple[int, int]] = {}
    stack_start: int | None = None
    for index, (body, _) in enumerate(parts):
        if body.strip() == b"0 stack":
            stack_start = index
            continue
        if not (match := _GSTAT_ASSIGNMENT.match(body)):
            continue
        field = match["field"].decode("ascii")
        if field in blocks:
            raise SaveError(f"全局升级存档字段重复：{field}")
        numeric = _GSTAT_FIELD.match(body) is not None
        if numeric:
            blocks[field] = (index, index)
        elif stack_start is not None:
            blocks[field] = (stack_start, index)
        else:
            raise SaveError(f"全局升级字段 {field} 使用了未识别的非数值保存格式，已拒绝转换。")
        stack_start = None
    if not blocks:
        raise SaveError("文件中未找到 gstats 字段，不是可识别的全局升级存档。")
    return parts, blocks


def assert_same_gstats_structure(source: bytes, target: bytes) -> None:
    """确认两份 gstats 所有字段一致，防止跨未兼容版本盲目覆盖。"""
    _, source_blocks = _gstats_field_blocks(source)
    _, target_blocks = _gstats_field_blocks(target)
    source_fields = tuple(source_blocks)
    target_fields = tuple(target_blocks)
    if source_fields != target_fields:
        raise SaveError("两份 gstats 字段结构不同，可能来自未兼容的游戏或补丁版本，已拒绝转换。")


def merge_gstats(source: bytes, target: bytes) -> tuple[bytes, GStatsMergeReport]:
    """将旧版本 gstats 安全迁移到字段更多的目标版本。

    字段完全一致时沿用完整复制。若来源字段是目标字段的有序子集，则以目标文件
    为模板：迁移所有同名字段，目标独有的数值字段写为 0。来源有目标不存在的字段、
    字段顺序改变，或目标独有字段不是可安全归零的数值字段时一律拒绝。
    """
    source_parts, source_blocks = _gstats_field_blocks(source)
    target_parts, target_blocks = _gstats_field_blocks(target)
    source_fields = tuple(source_blocks)
    target_fields = tuple(target_blocks)
    source_only = tuple(field for field in source_fields if field not in target_blocks)
    if source_only:
        raise SaveError(
            "来源 gstats 含有目标版本没有的字段，不能安全降级转换："
            + "、".join(source_only)
        )
    if source_fields == target_fields:
        return source, GStatsMergeReport("exact", len(source_fields))
    if source_fields != tuple(field for field in target_fields if field in source_blocks):
        raise SaveError("两份 gstats 的共同字段顺序不同，不能安全合并。")

    source_values = read_gstats(source)
    target_only = tuple(field for field in target_fields if field not in source_blocks)
    stack_replacements: dict[int, tuple[int, list[tuple[bytes, bytes]]]] = {}
    for field in source_fields:
        source_start, source_end = source_blocks[field]
        target_start, target_end = target_blocks[field]
        source_numeric = _GSTAT_FIELD.match(source_parts[source_end][0]) is not None
        target_numeric = _GSTAT_FIELD.match(target_parts[target_end][0]) is not None
        if source_numeric != target_numeric:
            raise SaveError(f"全局升级字段 {field} 的保存格式在两个版本间不同，已拒绝转换。")
        if not source_numeric:
            stack_replacements[target_start] = (target_end, source_parts[source_start:source_end + 1])
    for field in target_only:
        _, target_end = target_blocks[field]
        if _GSTAT_FIELD.match(target_parts[target_end][0]) is None:
            raise SaveError(f"目标新增字段 {field} 不是可安全归零的数值字段，已拒绝转换。")

    output: list[tuple[bytes, bytes]] = []
    index = 0
    while index < len(target_parts):
        if index in stack_replacements:
            end, replacement = stack_replacements[index]
            output.extend(replacement)
            index = end + 1
            continue
        body, ending = target_parts[index]
        if match := _GSTAT_FIELD.match(body):
            field = match["field"].decode("ascii")
            value = source_values[field] if field in source_values else 0
            body = _replace_value(body, match, str(value).encode("ascii"))
        output.append((body, ending))
        index += 1
    return _join(output), GStatsMergeReport("forward_merge", len(source_fields), target_only)


def set_gstats_fields(data: bytes, *, prefixes: tuple[str, ...], value: int) -> tuple[bytes, int]:
    """将以给定前缀开头的全局字段设为固定值，逐行二进制替换。"""
    read_gstats(data)  # 先验证，拒绝未知/空文件。
    output: list[tuple[bytes, bytes]] = []
    changed = 0
    for body, ending in _parts(data):
        if match := _GSTAT_FIELD.match(body):
            field = match["field"].decode("ascii")
            if field.startswith(prefixes):
                body = _replace_value(body, match, str(value).encode("ascii"))
                changed += 1
        output.append((body, ending))
    if not changed:
        raise SaveError(f"未找到前缀为 {', '.join(prefixes)} 的全局升级字段。")
    return _join(output), changed


def backup_and_replace(target: Path, data: bytes, *, backup_dir: Path | None = None) -> Path | None:
    """先将现有目标备份到软件目录，随后同目录临时文件原子替换。"""
    target = target.resolve()
    backup: Path | None = None
    if target.exists():
        backup_dir = backup_dir or BACKUP_DIR
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = backup_dir / f"{stamp}_{target.name}"
        shutil.copy2(target, backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        if hashlib.sha256(temporary.read_bytes()).digest() != hashlib.sha256(data).digest():
            raise SaveError("临时文件校验失败，未覆盖目标存档。")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return backup
