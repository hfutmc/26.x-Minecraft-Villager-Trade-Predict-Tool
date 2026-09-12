"""
MC 26.1 Villager Trade Prediction System
Based on decompiled 26.1 source (minecraft-merged-b5df1ea0fb-26.1.jar)

Seed derivation chain (verified from bytecode):
  worldSeed -> RandomSequences.get(id, worldSeed)
  -> createSequence(id, worldSeed)
     effectiveSeed = (includeWorldSeed ? worldSeed : 0) ^ salt  (salt=0, includeWorldSeed=True by default)
  -> RandomSequence(effectiveSeed, id)
     upgradeSeedTo128bitUnmixed(effectiveSeed) XOR seedForKey(id) -> mixed -> XoroshiroRandomSource

Trade generation chain (verified from bytecode):
  addOffersFromTradeSet -> LootContext.Builder.create(tradeSet.randomSequence)
  -> addOffersFromItemListingsWithoutDuplicates(lootContext, offers, trades, amount)
     picks = random.nextInt(remaining.size()) from remaining list, removes picked, calls getOffer(lootContext)

Enchanted book logic (verified from bytecode):
  EnchantRandomlyFunction.run():
    1. Select enchantment: Util.getRandomSafe(filteredOptions, random) -> nextInt(list.size())
    2. enchantItem():
       level = Mth.nextInt(random, minLevel, maxLevel) = minLevel + nextInt(maxLevel - minLevel + 1)
       if includeAdditionalCostComponent:
         ADDITIONAL_TRADE_COST = 2 + nextInt(5 + level * 10) + 3 * level
  VillagerTrade.getOffer():
    reads ADDITIONAL_TRADE_COST, adds to base price
    if double_trade_price_enchantments (treasure): price *= 2
"""

import struct
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

# ============================================================
# Constants from RandomSupport (verified from bytecode)
# ============================================================
SILVER_RATIO_64 = 0x6A09E667F3BCC909
GOLDEN_RATIO_64 = 0x9E3779B97F4A7C15
STAFFORD_MUL1 = 0xBF58476D1CE4E5B9
STAFFORD_MUL2 = 0x94D049BB133111EB

# Default values from RandomSequences 26.1
DEFAULT_SALT = 0
DEFAULT_INCLUDE_WORLD_SEED = True
DEFAULT_INCLUDE_SEQUENCE_ID = True


# ============================================================
# Unsigned 64-bit arithmetic helpers
# ============================================================
def u64(x: int) -> int:
    return x & 0xFFFFFFFFFFFFFFFF

def s64(x: int) -> int:
    x = x & 0xFFFFFFFFFFFFFFFF
    return x - 0x10000000000000000 if x >= 0x8000000000000000 else x

def rotl64(x: int, k: int) -> int:
    x = u64(x)
    return u64((x << k) | (x >> (64 - k)))


# ============================================================
# mixStafford13 (verified from bytecode)
# ============================================================
def mix_stafford13(z: int) -> int:
    z = u64(z)
    z = u64(u64(z ^ u64(z >> 30)) * STAFFORD_MUL1)
    z = u64(u64(z ^ u64(z >> 27)) * STAFFORD_MUL2)
    z = u64(z ^ u64(z >> 31))
    return z


# ============================================================
# Seed128bit record (verified from bytecode)
# ============================================================
@dataclass
class Seed128bit:
    lo: int
    hi: int

    def xor_other(self, other: 'Seed128bit') -> 'Seed128bit':
        return Seed128bit(u64(self.lo ^ other.lo), u64(self.hi ^ other.hi))

    def mixed(self) -> 'Seed128bit':
        return Seed128bit(mix_stafford13(self.lo), mix_stafford13(self.hi))


def upgrade_seed_to_128bit_unmixed(seed: int) -> Seed128bit:
    """Verified from RandomSupport.upgradeSeedTo128bitUnmixed bytecode."""
    seed = u64(seed)
    lo = u64(seed ^ SILVER_RATIO_64)
    hi = u64(lo + GOLDEN_RATIO_64)
    return Seed128bit(lo, hi)


def seed_from_hash_of(identifier: str) -> Seed128bit:
    """
    Verified from RandomSupport.seedFromHashOf bytecode.
    Uses Guava's MD5 + Longs.fromBytes (big-endian).
    """
    md5_digest = hashlib.md5(identifier.encode('utf-8')).digest()
    lo = u64(struct.unpack('>q', md5_digest[0:8])[0])
    hi = u64(struct.unpack('>q', md5_digest[8:16])[0])
    return Seed128bit(lo, hi)


def create_random_sequence_seed(world_seed: int, identifier: str,
                                 salt: int = DEFAULT_SALT,
                                 include_world_seed: bool = DEFAULT_INCLUDE_WORLD_SEED,
                                 include_sequence_id: bool = DEFAULT_INCLUDE_SEQUENCE_ID) -> Seed128bit:
    """Verified from RandomSequences.createSequence + RandomSequence constructor bytecode."""
    effective_seed = u64((world_seed if include_world_seed else 0) ^ salt)
    seed128 = upgrade_seed_to_128bit_unmixed(effective_seed)
    if include_sequence_id:
        seed128 = seed128.xor_other(seed_from_hash_of(identifier))
    return seed128.mixed()


# ============================================================
# Xoroshiro128++ PRNG (verified from bytecode)
# ============================================================
class Xoroshiro128PlusPlus:
    def __init__(self, seed_lo: int, seed_hi: int):
        self.lo = u64(seed_lo)
        self.hi = u64(seed_hi)
        if (self.lo | self.hi) == 0:
            self.lo = u64(0x9E3779B97F4A7C15)
            self.hi = u64(0x6A09E667F3BCC909)

    def next_long(self) -> int:
        l = self.lo
        m = self.hi
        n = u64(rotl64(u64(l + m), 17) + l)
        m = u64(m ^ l)
        self.lo = u64(rotl64(l, 49) ^ m ^ u64(m << 21))
        self.hi = rotl64(m, 28)
        return s64(n)

    def next_int(self, bound: Optional[int] = None) -> int:
        """Verified from XoroshiroRandomSource.nextInt bytecode."""
        if bound is None:
            return self.next_long() & 0xFFFFFFFF
        if bound <= 0:
            raise ValueError("Bound must be positive")
        r = self.next_long() & 0xFFFFFFFF
        product = u64(r * bound)
        low = product & 0xFFFFFFFF
        if low < bound:
            threshold = (0x100000000 - bound) % bound
            while low < threshold:
                r = self.next_long() & 0xFFFFFFFF
                product = u64(r * bound)
                low = product & 0xFFFFFFFF
        return (product >> 32) & 0xFFFFFFFF

    def next_float(self) -> float:
        """nextBits(24) >>> (64-24) = nextLong() >>> 40, then / 2^24"""
        bits = u64(self.next_long()) >> 40
        return bits * 5.9604645e-8


class XoroshiroRandomSource:
    def __init__(self, seed_lo: int, seed_hi: int):
        self.rng = Xoroshiro128PlusPlus(seed_lo, seed_hi)

    @classmethod
    def from_world_seed_and_id(cls, world_seed: int, identifier: str,
                                salt: int = DEFAULT_SALT,
                                include_world_seed: bool = DEFAULT_INCLUDE_WORLD_SEED,
                                include_sequence_id: bool = DEFAULT_INCLUDE_SEQUENCE_ID) -> 'XoroshiroRandomSource':
        seed128 = create_random_sequence_seed(world_seed, identifier, salt, include_world_seed, include_sequence_id)
        return cls(seed128.lo, seed128.hi)

    def next_int(self, bound: Optional[int] = None) -> int:
        return self.rng.next_int(bound)

    def next_long(self) -> int:
        return self.rng.next_long()

    def next_float(self) -> float:
        return self.rng.next_float()


# ============================================================
# Enchantment Data (from 26.1 jar: tags/enchantment/tradeable.json)
# #minecraft:tradeable = #minecraft:non_treasure + binding_curse, vanishing_curse, frost_walker, mending
# #minecraft:double_trade_price = #minecraft:treasure
# ============================================================

# From tags/enchantment/non_treasure.json (order matters - this is registry order)
NON_TREASURE_ENCHANTMENTS = [
    # (name, max_level)
    ("protection", 4),
    ("fire_protection", 4),
    ("feather_falling", 4),
    ("blast_protection", 4),
    ("projectile_protection", 4),
    ("respiration", 3),
    ("aqua_affinity", 1),
    ("thorns", 3),
    ("depth_strider", 3),
    ("sharpness", 5),
    ("smite", 5),
    ("bane_of_arthropods", 5),
    ("knockback", 2),
    ("fire_aspect", 2),
    ("looting", 3),
    ("sweeping_edge", 3),
    ("efficiency", 5),
    ("silk_touch", 1),
    ("unbreaking", 3),
    ("fortune", 3),
    ("power", 5),
    ("punch", 2),
    ("flame", 1),
    ("infinity", 1),
    ("luck_of_the_sea", 3),
    ("lure", 3),
    ("loyalty", 3),
    ("impaling", 5),
    ("riptide", 3),
    ("channeling", 1),
    ("multishot", 1),
    ("quick_charge", 3),
    ("piercing", 4),
    ("density", 5),
    ("breach", 4),
    ("lunge", 3),
]

# From tags/enchantment/treasure.json
TREASURE_ENCHANTMENTS = [
    ("binding_curse", 1),
    ("vanishing_curse", 1),
    ("swift_sneak", 3),
    ("soul_speed", 3),
    ("frost_walker", 2),
    ("mending", 1),
    ("wind_burst", 3),
]

# #minecraft:tradeable = non_treasure + binding_curse, vanishing_curse, frost_walker, mending
# (from tags/enchantment/tradeable.json)
TRADEABLE_ENCHANTMENTS = NON_TREASURE_ENCHANTMENTS + [
    ("binding_curse", 1),
    ("vanishing_curse", 1),
    ("frost_walker", 2),
    ("mending", 1),
]

# #minecraft:double_trade_price = #minecraft:treasure
DOUBLE_PRICE_SET = {"binding_curse", "vanishing_curse", "swift_sneak", "soul_speed",
                    "frost_walker", "mending", "wind_burst"}

TOTAL_TRADEABLE = len(TRADEABLE_ENCHANTMENTS)  # 40


def simulate_enchanted_book(rng: XoroshiroRandomSource, include_additional_cost: bool = True) -> dict:
    """
    Simulate enchant_randomly + enchantItem for an enchanted book trade.
    Verified from EnchantRandomlyFunction bytecode.

    Logic:
      1. pick enchantment: nextInt(list.size()) from tradeable list
         (since item is book and onlyCompatible=false, no filtering)
      2. level selection (Mth.nextInt):
         - if minLevel >= maxLevel: level = minLevel (no RNG draw)
         - else: level = minLevel + nextInt(maxLevel - minLevel + 1)
      3. if includeAdditionalCostComponent:
           ADDITIONAL_TRADE_COST = 2 + nextInt(5 + level * 10) + 3 * level
      4. In getOffer: base_price + ADDITIONAL_TRADE_COST
         if double_trade_price_enchantments: price *= 2
    """
    # Step 1: select enchantment from tradeable pool
    idx = rng.next_int(TOTAL_TRADEABLE)
    name, max_level = TRADEABLE_ENCHANTMENTS[idx]
    min_level = 1

    # Step 2: select level (Mth.nextInt)
    # CRITICAL: If minLevel >= maxLevel, NO RNG draw!
    if max_level > min_level:
        level = min_level + rng.next_int(max_level - min_level + 1)
    else:
        level = min_level  # No RNG consumed

    # Step 3: ADDITIONAL_TRADE_COST
    additional_cost = 0
    if include_additional_cost:
        additional_cost = 2 + rng.next_int(5 + level * 10) + 3 * level

    # Step 4: check double trade price
    is_double = name in DOUBLE_PRICE_SET
    final_cost = additional_cost * 2 if is_double else additional_cost
    final_cost = max(1, min(64, final_cost))

    return {
        "enchantment": name,
        "level": level,
        "max_level": max_level,
        "additional_cost": additional_cost,
        "final_cost": final_cost,
        "is_treasure": is_double,
        "pool_index": idx,
    }


# ============================================================
# Trade Pool Data (from 26.1 jar - verified)
# ============================================================
PROFESSIONS = [
    "armorer", "butcher", "cartographer", "cleric", "farmer",
    "fisherman", "fletcher", "leatherworker", "librarian", "mason",
    "shepherd", "toolsmith", "weaponsmith"
]

def trade_set_id(profession: str, level: int) -> str:
    return f"minecraft:trade_set/{profession}/level_{level}"


def is_enchanted_book_entry(entry_name: str) -> bool:
    """Check if a trade entry is an enchanted book trade."""
    return "enchanted_book" in entry_name


def is_enchanted_equipment_entry(entry_name: str) -> bool:
    """Check if a trade entry is an enchanted equipment trade (enchant_with_levels)."""
    return "enchanted" in entry_name and "book" not in entry_name


# Enchantment data for #minecraft:on_traded_equipment tag
# (from tags/enchantment/on_traded_equipment.json)
ON_TRADED_EQUIPMENT_ENCHANTMENTS = [
    ("protection", 4),
    ("fire_protection", 4),
    ("feather_falling", 4),
    ("blast_protection", 4),
    ("projectile_protection", 4),
    ("respiration", 3),
    ("aqua_affinity", 1),
    ("thorns", 3),
    ("sharpness", 5),
    ("smite", 5),
    ("bane_of_arthropods", 5),
    ("knockback", 2),
    ("fire_aspect", 2),
    ("looting", 3),
    ("efficiency", 5),
    ("silk_touch", 1),
    ("unbreaking", 3),
    ("fortune", 3),
    ("power", 5),
    ("punch", 2),
    ("flame", 1),
    ("infinity", 1),
    ("luck_of_the_sea", 3),
    ("lure", 3),
    ("loyalty", 3),
    ("impaling", 5),
    ("riptide", 3),
    ("channeling", 1),
    ("multishot", 1),
    ("quick_charge", 3),
    ("piercing", 4),
    ("density", 5),
    ("breach", 4),
    ("lunge", 3),
    ("sweeping_edge", 3),
    ("depth_strider", 3),
]


# Item enchantability values (needed for selectEnchantment simulation)
ITEM_ENCHANTABILITY = {
    "minecraft:iron_axe": 14, "minecraft:iron_shovel": 14, "minecraft:iron_pickaxe": 14,
    "minecraft:iron_sword": 14, "minecraft:iron_hoe": 14,
    "minecraft:diamond_axe": 10, "minecraft:diamond_shovel": 10, "minecraft:diamond_pickaxe": 10,
    "minecraft:diamond_sword": 10, "minecraft:diamond_hoe": 10,
    "minecraft:diamond_helmet": 10, "minecraft:diamond_chestplate": 10,
    "minecraft:diamond_leggings": 10, "minecraft:diamond_boots": 10,
    "minecraft:iron_helmet": 9, "minecraft:iron_chestplate": 9,
    "minecraft:iron_leggings": 9, "minecraft:iron_boots": 9,
    "minecraft:fishing_rod": 1, "minecraft:bow": 1, "minecraft:crossbow": 1,
    "minecraft:leather_helmet": 15, "minecraft:leather_chestplate": 15,
    "minecraft:leather_leggings": 15, "minecraft:leather_boots": 15,
}


# Enchantment incompatibility groups (mutually exclusive enchantments)
ENCHANTMENT_INCOMPATIBLE = {
    "protection": {"fire_protection", "blast_protection", "projectile_protection"},
    "fire_protection": {"protection", "blast_protection", "projectile_protection"},
    "blast_protection": {"protection", "fire_protection", "projectile_protection"},
    "projectile_protection": {"protection", "fire_protection", "blast_protection"},
    "sharpness": {"smite", "bane_of_arthropods"},
    "smite": {"sharpness", "bane_of_arthropods"},
    "bane_of_arthropods": {"sharpness", "smite"},
    "silk_touch": {"fortune"},
    "fortune": {"silk_touch"},
    "depth_strider": {"frost_walker"},
    "frost_walker": {"depth_strider"},
    "multishot": {"piercing"},
    "piercing": {"multishot"},
    "riptide": {"loyalty", "channeling"},
    "loyalty": {"riptide"},
    "channeling": {"riptide"},
}

# Enchantment rarity weights (from Enchantment.getWeight())
# COMMON=10, UNCOMMON=5, RARE=2, VERY_RARE=1
ENCHANTMENT_WEIGHTS = {
    "protection": 10, "fire_protection": 5, "feather_falling": 5, "blast_protection": 2,
    "projectile_protection": 5, "respiration": 2, "aqua_affinity": 2, "thorns": 1,
    "depth_strider": 2, "sharpness": 10, "smite": 5, "bane_of_arthropods": 5,
    "knockback": 5, "fire_aspect": 2, "looting": 2, "sweeping_edge": 2,
    "efficiency": 10, "silk_touch": 1, "unbreaking": 5, "fortune": 2,
    "power": 10, "punch": 2, "flame": 2, "infinity": 1,
    "luck_of_the_sea": 2, "lure": 2, "loyalty": 5, "impaling": 2,
    "riptide": 2, "channeling": 1, "multishot": 2, "quick_charge": 5,
    "piercing": 10, "density": 5, "breach": 2, "lunge": 2,
}

# Enchantment cost ranges (from Minecraft Enchantment class bytecode)
# Each enchantment has its own min/max cost per level for enchanting table lookup.
# Format: (base, per_lv_mult, extra_max) -> min=base+mult*(lv-1), max=min+extra_max
# If per_lv_mult == 0, min is fixed; if extra_max > 200, max is absolute value
_ENCHANT_COST_RANGES = {
    # ARMOR (default: 1+10*(lv-1), +15)
    "protection":              (1, 10, 15),
    "fire_protection":         (10, 8, 10),
    "feather_falling":         (5, 10, 10),
    "blast_protection":        (5, 8, 10),
    "projectile_protection":   (3, 6, 6),
    "respiration":             (10, 10, 30),
    "aqua_affinity":           (1, 0, 40),    # fixed: min=1, max=1+40=41
    "thorns":                  (10, 20, 50),
    "depth_strider":           (1, 10, 15),
    # SWORD
    "sharpness":               (1, 10, 15),
    "smite":                   (1, 10, 15),
    "bane_of_arthropods":      (1, 10, 15),
    "knockback":               (5, 20, 50),
    "fire_aspect":             (10, 20, 50),
    "looting":                 (15, 9, 50),
    "sweeping_edge":           (5, 9, 15),
    # TOOLS
    "efficiency":              (1, 10, 50),
    "silk_touch":              (15, 0, 50),   # fixed: min=15, max=15+50=65
    "unbreaking":              (5, 8, 50),
    "fortune":                 (15, 9, 50),
    # BOW
    "power":                   (1, 10, 15),
    "punch":                   (12, 20, 25),
    "flame":                   (10, 20, 50),
    "infinity":                (1, 10, 15),
    # FISHING
    "luck_of_the_sea":         (15, 9, 50),
    "lure":                    (15, 9, 50),
    # TRIDENT
    "loyalty":                 (5, 7, 50),    # max fixed at 50
    "impaling":                (1, 8, 20),
    "riptide":                 (10, 7, 50),   # max fixed at 50
    "channeling":              (12, 20, 50),  # max fixed at 50
    # CROSSBOW
    "multishot":               (10, 20, 50),  # max fixed at 50
    "quick_charge":            (12, 20, 50),  # max fixed at 50
    "piercing":                (1, 10, 50),   # max fixed at 50
    # 1.21
    "density":                 (1, 10, 15),
    "breach":                  (1, 10, 15),
    "lunge":                   (1, 10, 15),   # default (new enchantment)
}

def _enchantment_level_range(ench_name: str, ench_level: int) -> Tuple[int, int]:
    """Get the min/max cost range for a specific enchantment at a given level.
    Returns (min_cost, max_cost) for use in enchanting table lookup."""
    base, mult, extra = _ENCHANT_COST_RANGES.get(ench_name, (1, 10, 15))
    min_cost = base + mult * (ench_level - 1)
    max_cost = min_cost + extra
    return (min_cost, max_cost)


# Item-specific enchantment compatibility (which enchantments can go on which items)
ITEM_ENCHANTMENT_COMPAT = {
    "minecraft:iron_sword": {"sharpness", "smite", "bane_of_arthropods", "knockback", "fire_aspect", "looting", "sweeping_edge", "unbreaking"},
    "minecraft:diamond_sword": {"sharpness", "smite", "bane_of_arthropods", "knockback", "fire_aspect", "looting", "sweeping_edge", "unbreaking"},
    "minecraft:iron_axe": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:diamond_axe": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:stone_axe": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:iron_pickaxe": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:diamond_pickaxe": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:stone_pickaxe": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:iron_shovel": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:diamond_shovel": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:stone_shovel": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:stone_hoe": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:diamond_hoe": {"efficiency", "fortune", "silk_touch", "unbreaking"},
    "minecraft:diamond_helmet": {"protection", "fire_protection", "blast_protection", "projectile_protection", "respiration", "aqua_affinity", "thorns", "unbreaking"},
    "minecraft:diamond_chestplate": {"protection", "fire_protection", "blast_protection", "projectile_protection", "thorns", "unbreaking"},
    "minecraft:diamond_leggings": {"protection", "fire_protection", "blast_protection", "projectile_protection", "thorns", "unbreaking"},
    "minecraft:diamond_boots": {"protection", "fire_protection", "blast_protection", "projectile_protection", "feather_falling", "depth_strider", "thorns", "unbreaking"},
    "minecraft:bow": {"power", "punch", "flame", "infinity", "unbreaking"},
    "minecraft:crossbow": {"quick_charge", "multishot", "piercing", "unbreaking"},
    "minecraft:fishing_rod": {"luck_of_the_sea", "lure", "unbreaking"},
}


def simulate_enchanted_equipment(rng: XoroshiroRandomSource, item_id: str,
                                  levels_min: int = 5, levels_max: int = 19,
                                  include_additional_cost: bool = True,
                                  base_cost: int = 0,
                                  compat_override: Optional[set] = None) -> dict:
    """
    Simulate enchant_with_levels for equipment trades.
    
    Full Minecraft enchanting table algorithm (EnchantmentHelper.selectEnchantment):
      1. level = levels_min + nextInt(levels_max - levels_min + 1)
      2. modified_level = level + 1 + nextInt(ench/4+1) + nextInt(ench/4+1)
      3. f = (nextFloat() + nextFloat() - 1.0) * 0.15
      4. modified_level = clamp(round(modified_level * (1 + f)), 1, MAX)
      5. getAvailableEnchantmentResults(modified_level) → filter & calculate levels
      6. WeightedRandom.getRandomItem() → first enchantment
      7. While nextInt(50) <= modified_level: select more, modified_level /= 2
    """
    level = levels_min + rng.next_int(levels_max - levels_min + 1)
    enchantability = ITEM_ENCHANTABILITY.get(item_id, 10)
    
    if enchantability <= 0:
        return {"type": "enchanted_equipment", "item": item_id,
                "enchant_level_cost": level, "enchantments": [],
                "additional_cost": level, "final_cost": base_cost + level}
    
    # Modified level
    modified_level = level + 1 + rng.next_int(enchantability // 4 + 1) + rng.next_int(enchantability // 4 + 1)
    f = (rng.next_float() + rng.next_float() - 1.0) * 0.15
    modified_level = round(modified_level * (1.0 + f))
    modified_level = max(1, min(modified_level, 2147483647))
    
    # Build available enchantment list with levels
    # getAvailableEnchantmentResults: for each enchant, find the highest level
    # where minEnchantability <= modified_level <= maxEnchantability
    # Also filter by item compatibility
    item_compat = ITEM_ENCHANTMENT_COMPAT.get(item_id, set())
    if compat_override is not None:
        item_compat = compat_override
    available = []
    for ench_name, max_ench_level in ON_TRADED_EQUIPMENT_ENCHANTMENTS:
        if ench_name not in item_compat:
            continue  # enchantment not compatible with this item
        for lv in range(max_ench_level, 0, -1):
            min_cost, max_cost = _enchantment_level_range(ench_name, lv)
            if min_cost <= modified_level <= max_cost:
                available.append((ench_name, lv))
                break
    
    if not available:
        return {"type": "enchanted_equipment", "item": item_id,
                "enchant_level_cost": level, "enchantments": [],
                "additional_cost": level, "final_cost": base_cost + level}
    
    selected = []
    
    # First random enchantment (weighted)
    total_weight = sum(ENCHANTMENT_WEIGHTS.get(name, 10) for name, _ in available)
    roll = rng.next_int(total_weight)
    accumulated = 0
    picked_idx = 0
    for i, (name, lv) in enumerate(available):
        accumulated += ENCHANTMENT_WEIGHTS.get(name, 10)
        if roll < accumulated:
            picked_idx = i
            break
    
    picked_name, picked_level = available.pop(picked_idx)
    selected.append((picked_name, picked_level))
    
    # Additional enchantments
    while rng.next_int(50) <= modified_level:
        # Remove incompatible enchantments
        incompatible = ENCHANTMENT_INCOMPATIBLE.get(picked_name, set())
        available = [(n, l) for n, l in available 
                     if n not in incompatible and picked_name not in ENCHANTMENT_INCOMPATIBLE.get(n, set())]
        
        if not available:
            break
        
        total_weight = sum(ENCHANTMENT_WEIGHTS.get(name, 10) for name, _ in available)
        if total_weight <= 0:
            break
            
        roll = rng.next_int(total_weight)
        accumulated = 0
        for i, (name, lv) in enumerate(available):
            accumulated += ENCHANTMENT_WEIGHTS.get(name, 10)
            if roll < accumulated:
                picked_name, picked_level = available.pop(i)
                selected.append((picked_name, picked_level))
                break
        
        modified_level //= 2
    
    additional_cost = level if include_additional_cost else 0
    
    return {
        "type": "enchanted_equipment",
        "item": item_id,
        "enchant_level_cost": level,
        "enchantments": selected,
        "base_cost": base_cost,
        "additional_cost": additional_cost,
        "final_cost": base_cost + additional_cost,
    }


# ============================================================
# Complete Trade Pool Data for ALL professions (from 26.1 jar)
# ============================================================

ALL_TRADE_DATA = {
    "armorer": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:smith/1/coal_emerald",
                "minecraft:armorer/1/emerald_iron_leggings",
                "minecraft:armorer/1/emerald_iron_boots",
                "minecraft:armorer/1/emerald_iron_helmet",
                "minecraft:armorer/1/emerald_iron_chestplate",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:smith/2/iron_ingot_emerald",
                "minecraft:armorer/2/emerald_bell",
                "minecraft:armorer/2/emerald_chainmail_boots",
                "minecraft:armorer/2/emerald_chainmail_leggings",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:armorer/3/lava_bucket_emerald",
                "minecraft:armorer/3/emerald_chainmail_helmet",
                "minecraft:armorer/3/emerald_chainmail_chestplate",
                "minecraft:armorer/3/emerald_shield",
                "minecraft:armorer/3/diamond_emerald",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:armorer/4/emerald_enchanted_diamond_leggings",
                "minecraft:armorer/4/emerald_enchanted_diamond_boots",
            ],
            "enchanted_equipment_indices": [0, 1],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:armorer/5/emerald_enchanted_diamond_helmet",
                "minecraft:armorer/5/emerald_enchanted_diamond_chestplate",
            ],
            "enchanted_equipment_indices": [0, 1],
        },
    },
    "butcher": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:butcher/1/chicken_emerald",
                "minecraft:butcher/1/porkchop_emerald",
                "minecraft:butcher/1/rabbit_emerald",
                "minecraft:butcher/1/emerald_rabbit_stew",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:butcher/2/coal_emerald",
                "minecraft:butcher/2/emerald_cooked_porkchop",
                "minecraft:butcher/2/emerald_cooked_chicken",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:butcher/3/mutton_emerald",
                "minecraft:butcher/3/beef_emerald",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:butcher/4/dried_kelp_block_emerald",
            ],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:butcher/5/sweet_berries_emerald",
            ],
        },
    },
    "cartographer": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:cartographer/1/paper_emerald",
                "minecraft:cartographer/1/emerald_map",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:cartographer/2/glass_pane_emerald",
                "minecraft:cartographer/2/emerald_and_compass_village_taiga_map",
                "minecraft:cartographer/2/emerald_and_compass_explorer_swamp_map",
                "minecraft:cartographer/2/emerald_and_compass_village_snowy_map",
                "minecraft:cartographer/2/emerald_and_compass_village_savanna_map",
                "minecraft:cartographer/2/emerald_and_compass_village_plains_map",
                "minecraft:cartographer/2/emerald_and_compass_explorer_jungle_map",
                "minecraft:cartographer/2/emerald_and_compass_village_desert_map",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:cartographer/3/compass_emerald",
                "minecraft:cartographer/3/emerald_and_compass_ocean_explorer_map",
                "minecraft:cartographer/3/emerald_and_compass_trial_chamber_map",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:cartographer/4/emerald_item_frame",
                "minecraft:cartographer/4/emerald_white_banner",
                "minecraft:cartographer/4/emerald_orange_banner",
                "minecraft:cartographer/4/emerald_magenta_banner",
                "minecraft:cartographer/4/emerald_blue_banner",
                "minecraft:cartographer/4/emerald_light_blue_banner",
                "minecraft:cartographer/4/emerald_yellow_banner",
                "minecraft:cartographer/4/emerald_lime_banner",
                "minecraft:cartographer/4/emerald_pink_banner",
                "minecraft:cartographer/4/emerald_gray_banner",
                "minecraft:cartographer/4/emerald_cyan_banner",
                "minecraft:cartographer/4/emerald_purple_banner",
                "minecraft:cartographer/4/emerald_brown_banner",
                "minecraft:cartographer/4/emerald_green_banner",
                "minecraft:cartographer/4/emerald_red_banner",
                "minecraft:cartographer/4/emerald_black_banner",
            ],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:cartographer/5/emerald_globe_banner_pattern",
                "minecraft:cartographer/5/emerald_and_compass_woodland_mansion_map",
            ],
        },
    },
    "cleric": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:cleric/1/rotten_flesh_emerald",
                "minecraft:cleric/1/emerald_redstone",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:cleric/2/gold_ingot_emerald",
                "minecraft:cleric/2/emerald_lapis_lazuli",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:cleric/3/rabbit_foot_emerald",
                "minecraft:cleric/3/emerald_glowstone",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:cleric/4/turtle_scute_emerald",
                "minecraft:cleric/4/glass_bottle_emerald",
                "minecraft:cleric/4/emerald_ender_pearl",
            ],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:cleric/5/nether_wart_emerald",
                "minecraft:cleric/5/emerald_experience_bottle",
            ],
        },
    },
    "farmer": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:farmer/1/wheat_emerald",
                "minecraft:farmer/1/potato_emerald",
                "minecraft:farmer/1/carrot_emerald",
                "minecraft:farmer/1/beetroot_emerald",
                "minecraft:farmer/1/emerald_bread",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:farmer/2/pumpkin_emerald",
                "minecraft:farmer/2/emerald_pumpkin_pie",
                "minecraft:farmer/2/emerald_apple",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:farmer/3/emerald_cookie",
                "minecraft:farmer/3/melon_emerald",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:farmer/4/emerald_cake",
                "minecraft:farmer/4/emerald_suspicious_stew",
            ],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:farmer/5/emerald_golden_carrot",
                "minecraft:farmer/5/emerald_glistening_melon_slice",
            ],
        },
    },
    "fisherman": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:fisherman/1/string_emerald",
                "minecraft:fisherman/1/coal_emerald",
                "minecraft:fisherman/1/raw_cod_and_emerald_cooked_cod",
                "minecraft:fisherman/1/emerald_cod_bucket",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:fisherman/2/cod_emerald",
                "minecraft:fisherman/2/salmon_and_emerald_cooked_salmon",
                "minecraft:fisherman/2/emerald_campfire",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:fisherman/3/salmon_emerald",
                "minecraft:fisherman/3/emerald_enchanted_fishing_rod",
            ],
            "enchanted_equipment_indices": [1],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:fisherman/4/tropical_fish_emerald",
            ],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:fisherman/5/pufferfish_emerald",
                "minecraft:fisherman/5/oak_boat_emerald",
                "minecraft:fisherman/5/spruce_boat_emerald",
                "minecraft:fisherman/5/jungle_boat_emerald",
                "minecraft:fisherman/5/acacia_boat_emerald",
                "minecraft:fisherman/5/dark_oak_boat_emerald",
            ],
        },
    },
    "fletcher": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:fletcher/1/stick_emerald",
                "minecraft:fletcher/1/emerald_arrow",
                "minecraft:fletcher/1/gravel_and_emerald_flint",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:fletcher/2/flint_emerald",
                "minecraft:fletcher/2/emerald_bow",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:fletcher/3/string_emerald",
                "minecraft:fletcher/3/emerald_crossbow",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:fletcher/4/feather_emerald",
                "minecraft:fletcher/4/emerald_enchanted_bow",
            ],
            "enchanted_equipment_indices": [1],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:fletcher/5/tripwire_hook_emerald",
                "minecraft:fletcher/5/emerald_enchanted_crossbow",
                "minecraft:fletcher/5/arrow_and_emerald_tipped_arrow",
            ],
            "enchanted_equipment_indices": [1],
        },
    },
    "leatherworker": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:leatherworker/1/leather_emerald",
                "minecraft:leatherworker/1/emerald_dyed_leather_leggings",
                "minecraft:leatherworker/1/emerald_dyed_leather_chestplate",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:leatherworker/2/flint_emerald",
                "minecraft:leatherworker/2/emerald_dyed_leather_helmet",
                "minecraft:leatherworker/2/emerald_dyed_leather_boots",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:leatherworker/3/rabbit_hide_emerald",
                "minecraft:leatherworker/3/emerald_dyed_leather_chestplate",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:leatherworker/4/turtle_scute_emerald",
                "minecraft:leatherworker/4/emerald_dyed_leather_horse_armor",
            ],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:leatherworker/5/emerald_saddle",
                "minecraft:leatherworker/5/emerald_dyed_leather_helmet",
            ],
        },
    },
    "librarian": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:librarian/1/paper_emerald",
                "minecraft:librarian/1/emerald_and_book_enchanted_book",
                "minecraft:librarian/1/emerald_bookshelf",
            ],
            "enchanted_book_indices": [1],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:librarian/2/book_emerald",
                "minecraft:librarian/2/emerald_and_book_enchanted_book",
                "minecraft:librarian/2/emerald_lantern",
            ],
            "enchanted_book_indices": [1],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:librarian/3/ink_sac_emerald",
                "minecraft:librarian/3/emerald_and_book_enchanted_book",
                "minecraft:librarian/3/emerald_glass",
            ],
            "enchanted_book_indices": [1],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:librarian/4/writable_book_emerald",
                "minecraft:librarian/4/emerald_book_and_enchanted_book",
                "minecraft:librarian/4/emerald_clock",
                "minecraft:librarian/4/emerald_compass",
            ],
            "enchanted_book_indices": [1],
        },
        5: {
            "amount": 3,
            "pool": [
                "minecraft:librarian/5/emerald_yellow_candle",
                "minecraft:librarian/5/emerald_red_candle",
            ],
        },
    },
    "mason": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:mason/1/clay_ball_emerald",
                "minecraft:mason/1/emerald_brick",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:mason/2/stone_emerald",
                "minecraft:mason/2/emerald_chiseled_stone_bricks",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:mason/3/granite_emerald",
                "minecraft:mason/3/andesite_emerald",
                "minecraft:mason/3/diorite_emerald",
                "minecraft:mason/3/emerald_dripstone_block",
                "minecraft:mason/3/emerald_polished_andesite",
                "minecraft:mason/3/emerald_polished_diorite",
                "minecraft:mason/3/emerald_polished_granite",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:mason/4/quartz_emerald",
                "minecraft:mason/4/emerald_orange_terracotta",
                "minecraft:mason/4/emerald_white_terracotta",
                "minecraft:mason/4/emerald_blue_terracotta",
                "minecraft:mason/4/emerald_light_blue_terracotta",
                "minecraft:mason/4/emerald_gray_terracotta",
                "minecraft:mason/4/emerald_light_gray_terracotta",
                "minecraft:mason/4/emerald_black_terracotta",
                "minecraft:mason/4/emerald_red_terracotta",
                "minecraft:mason/4/emerald_pink_terracotta",
                "minecraft:mason/4/emerald_magenta_terracotta",
                "minecraft:mason/4/emerald_lime_terracotta",
                "minecraft:mason/4/emerald_green_terracotta",
                "minecraft:mason/4/emerald_cyan_terracotta",
                "minecraft:mason/4/emerald_purple_terracotta",
                "minecraft:mason/4/emerald_yellow_terracotta",
                "minecraft:mason/4/emerald_brown_terracotta",
                "minecraft:mason/4/emerald_orange_glazed_terracotta",
                "minecraft:mason/4/emerald_white_glazed_terracotta",
                "minecraft:mason/4/emerald_blue_glazed_terracotta",
                "minecraft:mason/4/emerald_light_blue_glazed_terracotta",
                "minecraft:mason/4/emerald_gray_glazed_terracotta",
                "minecraft:mason/4/emerald_light_gray_glazed_terracotta",
                "minecraft:mason/4/emerald_black_glazed_terracotta",
                "minecraft:mason/4/emerald_red_glazed_terracotta",
                "minecraft:mason/4/emerald_pink_glazed_terracotta",
                "minecraft:mason/4/emerald_magenta_glazed_terracotta",
                "minecraft:mason/4/emerald_lime_glazed_terracotta",
                "minecraft:mason/4/emerald_green_glazed_terracotta",
                "minecraft:mason/4/emerald_cyan_glazed_terracotta",
                "minecraft:mason/4/emerald_purple_glazed_terracotta",
                "minecraft:mason/4/emerald_yellow_glazed_terracotta",
                "minecraft:mason/4/emerald_brown_glazed_terracotta",
            ],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:mason/5/emerald_quartz_pillar",
                "minecraft:mason/5/emerald_quartz_block",
            ],
        },
    },
    "shepherd": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:shepherd/1/white_wool_emerald",
                "minecraft:shepherd/1/brown_wool_emerald",
                "minecraft:shepherd/1/gray_wool_emerald",
                "minecraft:shepherd/1/black_wool_emerald",
                "minecraft:shepherd/1/emerald_shears",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:shepherd/2/white_dye_emerald",
                "minecraft:shepherd/2/gray_dye_emerald",
                "minecraft:shepherd/2/black_dye_emerald",
                "minecraft:shepherd/2/light_blue_dye_emerald",
                "minecraft:shepherd/2/lime_dye_emerald",
                "minecraft:shepherd/2/emerald_white_wool",
                "minecraft:shepherd/2/emerald_orange_wool",
                "minecraft:shepherd/2/emerald_magenta_wool",
                "minecraft:shepherd/2/emerald_blue_wool",
                "minecraft:shepherd/2/emerald_light_blue_wool",
                "minecraft:shepherd/2/emerald_yellow_wool",
                "minecraft:shepherd/2/emerald_lime_wool",
                "minecraft:shepherd/2/emerald_pink_wool",
                "minecraft:shepherd/2/emerald_gray_wool",
                "minecraft:shepherd/2/emerald_light_gray_wool",
                "minecraft:shepherd/2/emerald_cyan_wool",
                "minecraft:shepherd/2/emerald_purple_wool",
                "minecraft:shepherd/2/emerald_brown_wool",
                "minecraft:shepherd/2/emerald_green_wool",
                "minecraft:shepherd/2/emerald_red_wool",
                "minecraft:shepherd/2/emerald_black_wool",
                "minecraft:shepherd/2/emerald_white_carpet",
                "minecraft:shepherd/2/emerald_orange_carpet",
                "minecraft:shepherd/2/emerald_magenta_carpet",
                "minecraft:shepherd/2/emerald_blue_carpet",
                "minecraft:shepherd/2/emerald_light_blue_carpet",
                "minecraft:shepherd/2/emerald_yellow_carpet",
                "minecraft:shepherd/2/emerald_lime_carpet",
                "minecraft:shepherd/2/emerald_pink_carpet",
                "minecraft:shepherd/2/emerald_gray_carpet",
                "minecraft:shepherd/2/emerald_light_gray_carpet",
                "minecraft:shepherd/2/emerald_cyan_carpet",
                "minecraft:shepherd/2/emerald_purple_carpet",
                "minecraft:shepherd/2/emerald_brown_carpet",
                "minecraft:shepherd/2/emerald_green_carpet",
                "minecraft:shepherd/2/emerald_red_carpet",
                "minecraft:shepherd/2/emerald_black_carpet",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:shepherd/3/yellow_dye_emerald",
                "minecraft:shepherd/3/light_gray_dye_emerald",
                "minecraft:shepherd/3/orange_dye_emerald",
                "minecraft:shepherd/3/red_dye_emerald",
                "minecraft:shepherd/3/pink_dye_emerald",
                "minecraft:shepherd/3/emerald_white_bed",
                "minecraft:shepherd/3/emerald_orange_bed",
                "minecraft:shepherd/3/emerald_magenta_bed",
                "minecraft:shepherd/3/emerald_blue_bed",
                "minecraft:shepherd/3/emerald_light_blue_bed",
                "minecraft:shepherd/3/emerald_yellow_bed",
                "minecraft:shepherd/3/emerald_lime_bed",
                "minecraft:shepherd/3/emerald_pink_bed",
                "minecraft:shepherd/3/emerald_gray_bed",
                "minecraft:shepherd/3/emerald_light_gray_bed",
                "minecraft:shepherd/3/emerald_cyan_bed",
                "minecraft:shepherd/3/emerald_purple_bed",
                "minecraft:shepherd/3/emerald_brown_bed",
                "minecraft:shepherd/3/emerald_green_bed",
                "minecraft:shepherd/3/emerald_red_bed",
                "minecraft:shepherd/3/emerald_black_bed",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:shepherd/4/brown_dye_emerald",
                "minecraft:shepherd/4/purple_dye_emerald",
                "minecraft:shepherd/4/blue_dye_emerald",
                "minecraft:shepherd/4/green_dye_emerald",
                "minecraft:shepherd/4/magenta_dye_emerald",
                "minecraft:shepherd/4/cyan_dye_emerald",
                "minecraft:shepherd/4/emerald_white_banner",
                "minecraft:shepherd/4/emerald_orange_banner",
                "minecraft:shepherd/4/emerald_magenta_banner",
                "minecraft:shepherd/4/emerald_blue_banner",
                "minecraft:shepherd/4/emerald_light_blue_banner",
                "minecraft:shepherd/4/emerald_yellow_banner",
                "minecraft:shepherd/4/emerald_lime_banner",
                "minecraft:shepherd/4/emerald_pink_banner",
                "minecraft:shepherd/4/emerald_gray_banner",
                "minecraft:shepherd/4/emerald_light_gray_banner",
                "minecraft:shepherd/4/emerald_cyan_banner",
                "minecraft:shepherd/4/emerald_purple_banner",
                "minecraft:shepherd/4/emerald_brown_banner",
                "minecraft:shepherd/4/emerald_green_banner",
                "minecraft:shepherd/4/emerald_red_banner",
                "minecraft:shepherd/4/emerald_black_banner",
            ],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:shepherd/5/emerald_painting",
            ],
        },
    },
    "toolsmith": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:smith/1/coal_emerald",
                "minecraft:toolsmith/1/emerald_stone_axe",
                "minecraft:toolsmith/1/emerald_stone_shovel",
                "minecraft:toolsmith/1/emerald_stone_pickaxe",
                "minecraft:toolsmith/1/emerald_stone_hoe",
            ],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:smith/2/iron_ingot_emerald",
                "minecraft:smith/2/emerald_bell",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:toolsmith/3/flint_emerald",
                "minecraft:toolsmith/3/emerald_enchanted_iron_axe",
                "minecraft:toolsmith/3/emerald_enchanted_iron_shovel",
                "minecraft:toolsmith/3/emerald_enchanted_iron_pickaxe",
                "minecraft:toolsmith/3/emerald_diamond_hoe",
            ],
            "enchanted_equipment_indices": [1, 2, 3],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:toolsmith/4/emerald_enchanted_diamond_axe",
                "minecraft:toolsmith/4/emerald_enchanted_diamond_shovel",
                "minecraft:toolsmith/4/diamond_emerald",
            ],
            "enchanted_equipment_indices": [0, 1],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:toolsmith/5/emerald_enchanted_diamond_pickaxe",
            ],
            "enchanted_equipment_indices": [0],
        },
    },
    "weaponsmith": {
        1: {
            "amount": 2,
            "pool": [
                "minecraft:smith/1/coal_emerald",
                "minecraft:weaponsmith/1/emerald_iron_axe",
                "minecraft:weaponsmith/1/emerald_enchanted_iron_sword",
            ],
            "enchanted_equipment_indices": [2],
        },
        2: {
            "amount": 2,
            "pool": [
                "minecraft:smith/2/iron_ingot_emerald",
                "minecraft:smith/2/emerald_bell",
            ],
        },
        3: {
            "amount": 2,
            "pool": [
                "minecraft:weaponsmith/3/flint_emerald",
            ],
        },
        4: {
            "amount": 2,
            "pool": [
                "minecraft:weaponsmith/4/emerald_enchanted_diamond_axe",
                "minecraft:weaponsmith/4/diamond_emerald",
            ],
            "enchanted_equipment_indices": [0],
        },
        5: {
            "amount": 2,
            "pool": [
                "minecraft:weaponsmith/5/emerald_enchanted_diamond_sword",
            ],
            "enchanted_equipment_indices": [0],
        },
    },
}

# Enchanted equipment trade details: (item_id, levels_min, levels_max, base_emerald_cost)
# From trade_data_dump.py - extracted from actual jar JSON
ENCHANTED_EQUIPMENT_PARAMS = {
    # armorer level 4
    "minecraft:armorer/4/emerald_enchanted_diamond_leggings": ("minecraft:diamond_leggings", 5, 19, 14),
    "minecraft:armorer/4/emerald_enchanted_diamond_boots": ("minecraft:diamond_boots", 5, 19, 8),
    # armorer level 5
    "minecraft:armorer/5/emerald_enchanted_diamond_helmet": ("minecraft:diamond_helmet", 5, 19, 8),
    "minecraft:armorer/5/emerald_enchanted_diamond_chestplate": ("minecraft:diamond_chestplate", 5, 19, 16),
    # fisherman level 3
    "minecraft:fisherman/3/emerald_enchanted_fishing_rod": ("minecraft:fishing_rod", 5, 19, 3),
    # fletcher level 4
    "minecraft:fletcher/4/emerald_enchanted_bow": ("minecraft:bow", 5, 19, 2),
    # fletcher level 5
    "minecraft:fletcher/5/emerald_enchanted_crossbow": ("minecraft:crossbow", 5, 19, 3),
    # toolsmith level 3
    "minecraft:toolsmith/3/emerald_enchanted_iron_axe": ("minecraft:iron_axe", 5, 19, 1),
    "minecraft:toolsmith/3/emerald_enchanted_iron_shovel": ("minecraft:iron_shovel", 5, 19, 2),
    "minecraft:toolsmith/3/emerald_enchanted_iron_pickaxe": ("minecraft:iron_pickaxe", 5, 19, 3),
    # toolsmith level 4 (axes are tool-only)
    "minecraft:toolsmith/4/emerald_enchanted_diamond_axe": ("minecraft:diamond_axe", 5, 19, 12),
    "minecraft:toolsmith/4/emerald_enchanted_diamond_shovel": ("minecraft:diamond_shovel", 5, 19, 5),
    # toolsmith level 5
    "minecraft:toolsmith/5/emerald_enchanted_diamond_pickaxe": ("minecraft:diamond_pickaxe", 5, 19, 13),
    # weaponsmith level 1
    "minecraft:weaponsmith/1/emerald_enchanted_iron_sword": ("minecraft:iron_sword", 5, 19, 2),
    # weaponsmith level 4 (axes from weaponsmith get weapon enchants)
    "minecraft:weaponsmith/4/emerald_enchanted_diamond_axe": ("minecraft:diamond_axe", 5, 19, 12),
    # weaponsmith level 5
    "minecraft:weaponsmith/5/emerald_enchanted_diamond_sword": ("minecraft:diamond_sword", 5, 19, 8),
}

# Weapon enchantments available on axes from weaponsmith (but not toolsmith)
WEAPON_AXE_ENCHANTS = {"sharpness", "smite", "bane_of_arthropods", "unbreaking"}

# ============================================================
# Game version support (pool order differences)
# 26.1 -> 26.2: 4 pools were reordered (members unchanged), verified by
# diffing data/minecraft/tags/villager_trade between 26.1.2.jar and 26.2.jar:
#   mason L4, shepherd L2/L3/L4. All other pools are identical.
# Entry content changes in 26.2 (merchant_predicate namespacing, fletcher L5
# wants swap) do not affect RNG consumption, so pool order is the only
# difference that matters for prediction.
# ============================================================

GAME_VERSION_26_1 = "26.1"
GAME_VERSION_26_2 = "26.2"
GAME_VERSIONS = (GAME_VERSION_26_1, GAME_VERSION_26_2)
DEFAULT_GAME_VERSION = GAME_VERSION_26_1

# Full 26.2 pool order for the 4 reordered pools (taken from 26.2.jar tags)
POOL_ORDER_26_2 = {
    "mason": {
        4: [
            "minecraft:mason/4/quartz_emerald",
            "minecraft:mason/4/emerald_white_terracotta",
            "minecraft:mason/4/emerald_orange_terracotta",
            "minecraft:mason/4/emerald_magenta_terracotta",
            "minecraft:mason/4/emerald_light_blue_terracotta",
            "minecraft:mason/4/emerald_yellow_terracotta",
            "minecraft:mason/4/emerald_lime_terracotta",
            "minecraft:mason/4/emerald_pink_terracotta",
            "minecraft:mason/4/emerald_gray_terracotta",
            "minecraft:mason/4/emerald_light_gray_terracotta",
            "minecraft:mason/4/emerald_cyan_terracotta",
            "minecraft:mason/4/emerald_purple_terracotta",
            "minecraft:mason/4/emerald_blue_terracotta",
            "minecraft:mason/4/emerald_brown_terracotta",
            "minecraft:mason/4/emerald_green_terracotta",
            "minecraft:mason/4/emerald_red_terracotta",
            "minecraft:mason/4/emerald_black_terracotta",
            "minecraft:mason/4/emerald_white_glazed_terracotta",
            "minecraft:mason/4/emerald_orange_glazed_terracotta",
            "minecraft:mason/4/emerald_magenta_glazed_terracotta",
            "minecraft:mason/4/emerald_light_blue_glazed_terracotta",
            "minecraft:mason/4/emerald_yellow_glazed_terracotta",
            "minecraft:mason/4/emerald_lime_glazed_terracotta",
            "minecraft:mason/4/emerald_pink_glazed_terracotta",
            "minecraft:mason/4/emerald_gray_glazed_terracotta",
            "minecraft:mason/4/emerald_light_gray_glazed_terracotta",
            "minecraft:mason/4/emerald_cyan_glazed_terracotta",
            "minecraft:mason/4/emerald_purple_glazed_terracotta",
            "minecraft:mason/4/emerald_blue_glazed_terracotta",
            "minecraft:mason/4/emerald_brown_glazed_terracotta",
            "minecraft:mason/4/emerald_green_glazed_terracotta",
            "minecraft:mason/4/emerald_red_glazed_terracotta",
            "minecraft:mason/4/emerald_black_glazed_terracotta",
        ],
    },
    "shepherd": {
        2: [
            "minecraft:shepherd/2/white_dye_emerald",
            "minecraft:shepherd/2/gray_dye_emerald",
            "minecraft:shepherd/2/black_dye_emerald",
            "minecraft:shepherd/2/light_blue_dye_emerald",
            "minecraft:shepherd/2/lime_dye_emerald",
            "minecraft:shepherd/2/emerald_white_wool",
            "minecraft:shepherd/2/emerald_orange_wool",
            "minecraft:shepherd/2/emerald_magenta_wool",
            "minecraft:shepherd/2/emerald_light_blue_wool",
            "minecraft:shepherd/2/emerald_yellow_wool",
            "minecraft:shepherd/2/emerald_lime_wool",
            "minecraft:shepherd/2/emerald_pink_wool",
            "minecraft:shepherd/2/emerald_gray_wool",
            "minecraft:shepherd/2/emerald_light_gray_wool",
            "minecraft:shepherd/2/emerald_cyan_wool",
            "minecraft:shepherd/2/emerald_purple_wool",
            "minecraft:shepherd/2/emerald_blue_wool",
            "minecraft:shepherd/2/emerald_brown_wool",
            "minecraft:shepherd/2/emerald_green_wool",
            "minecraft:shepherd/2/emerald_red_wool",
            "minecraft:shepherd/2/emerald_black_wool",
            "minecraft:shepherd/2/emerald_white_carpet",
            "minecraft:shepherd/2/emerald_orange_carpet",
            "minecraft:shepherd/2/emerald_magenta_carpet",
            "minecraft:shepherd/2/emerald_light_blue_carpet",
            "minecraft:shepherd/2/emerald_yellow_carpet",
            "minecraft:shepherd/2/emerald_lime_carpet",
            "minecraft:shepherd/2/emerald_pink_carpet",
            "minecraft:shepherd/2/emerald_gray_carpet",
            "minecraft:shepherd/2/emerald_light_gray_carpet",
            "minecraft:shepherd/2/emerald_cyan_carpet",
            "minecraft:shepherd/2/emerald_purple_carpet",
            "minecraft:shepherd/2/emerald_blue_carpet",
            "minecraft:shepherd/2/emerald_brown_carpet",
            "minecraft:shepherd/2/emerald_green_carpet",
            "minecraft:shepherd/2/emerald_red_carpet",
            "minecraft:shepherd/2/emerald_black_carpet",
        ],
        3: [
            "minecraft:shepherd/3/yellow_dye_emerald",
            "minecraft:shepherd/3/light_gray_dye_emerald",
            "minecraft:shepherd/3/orange_dye_emerald",
            "minecraft:shepherd/3/red_dye_emerald",
            "minecraft:shepherd/3/pink_dye_emerald",
            "minecraft:shepherd/3/emerald_white_bed",
            "minecraft:shepherd/3/emerald_orange_bed",
            "minecraft:shepherd/3/emerald_magenta_bed",
            "minecraft:shepherd/3/emerald_light_blue_bed",
            "minecraft:shepherd/3/emerald_yellow_bed",
            "minecraft:shepherd/3/emerald_lime_bed",
            "minecraft:shepherd/3/emerald_pink_bed",
            "minecraft:shepherd/3/emerald_gray_bed",
            "minecraft:shepherd/3/emerald_light_gray_bed",
            "minecraft:shepherd/3/emerald_cyan_bed",
            "minecraft:shepherd/3/emerald_purple_bed",
            "minecraft:shepherd/3/emerald_blue_bed",
            "minecraft:shepherd/3/emerald_brown_bed",
            "minecraft:shepherd/3/emerald_green_bed",
            "minecraft:shepherd/3/emerald_red_bed",
            "minecraft:shepherd/3/emerald_black_bed",
        ],
        4: [
            "minecraft:shepherd/4/brown_dye_emerald",
            "minecraft:shepherd/4/purple_dye_emerald",
            "minecraft:shepherd/4/blue_dye_emerald",
            "minecraft:shepherd/4/green_dye_emerald",
            "minecraft:shepherd/4/magenta_dye_emerald",
            "minecraft:shepherd/4/cyan_dye_emerald",
            "minecraft:shepherd/4/emerald_white_banner",
            "minecraft:shepherd/4/emerald_orange_banner",
            "minecraft:shepherd/4/emerald_magenta_banner",
            "minecraft:shepherd/4/emerald_light_blue_banner",
            "minecraft:shepherd/4/emerald_yellow_banner",
            "minecraft:shepherd/4/emerald_lime_banner",
            "minecraft:shepherd/4/emerald_pink_banner",
            "minecraft:shepherd/4/emerald_gray_banner",
            "minecraft:shepherd/4/emerald_light_gray_banner",
            "minecraft:shepherd/4/emerald_cyan_banner",
            "minecraft:shepherd/4/emerald_purple_banner",
            "minecraft:shepherd/4/emerald_blue_banner",
            "minecraft:shepherd/4/emerald_brown_banner",
            "minecraft:shepherd/4/emerald_green_banner",
            "minecraft:shepherd/4/emerald_red_banner",
            "minecraft:shepherd/4/emerald_black_banner",
        ],
    },
}


def apply_pool_order(pool: list, profession: str, level: int,
                     game_version: str) -> list:
    """Return the pool adjusted for the game version (26.1 data is the base)."""
    if game_version != GAME_VERSION_26_2:
        return pool
    override = POOL_ORDER_26_2.get(profession, {}).get(level)
    if override is None:
        return pool
    return list(override)


def _validate_pool_order_26_2():
    """Fail fast at import if the 26.2 overrides don't match the 26.1 members."""
    for prof, levels in POOL_ORDER_26_2.items():
        for level, new_order in levels.items():
            old = ALL_TRADE_DATA.get(prof, {}).get(level, {}).get("pool", [])
            if sorted(old) != sorted(new_order):
                raise ValueError(
                    f"POOL_ORDER_26_2 members mismatch ALL_TRADE_DATA for "
                    f"{prof} L{level}"
                )


_validate_pool_order_26_2()


# ============================================================
# Variant filtering (merchant_predicate)
# ============================================================
# Each variant only sees a subset of the full trade pool.
# Key: (profession, level) -> {variant: [matching_entry_suffixes]}
VARIANT_FILTERS = {
    ("cartographer", 2): {
        "desert":  ["glass_pane_emerald", "village_plains_map",    "explorer_jungle_map",  "village_savanna_map"],
        "jungle":  ["glass_pane_emerald", "explorer_swamp_map",    "village_savanna_map",  "village_desert_map"],
        "plains":  ["glass_pane_emerald", "village_taiga_map",     "village_savanna_map"],
        "savanna": ["glass_pane_emerald", "village_plains_map",    "explorer_jungle_map",  "village_desert_map"],
        "snow":    ["glass_pane_emerald", "village_taiga_map",     "explorer_swamp_map",   "village_plains_map"],
        "swamp":   ["glass_pane_emerald", "village_taiga_map",     "village_snowy_map",    "explorer_jungle_map"],
        "taiga":   ["glass_pane_emerald", "explorer_swamp_map",    "village_snowy_map",    "village_plains_map"],
    },
    # Cartographer L4: each variant sees item_frame + 2 banners (3 entries total)
    ("cartographer", 4): {
        "desert":  ["emerald_item_frame", "emerald_green_banner", "emerald_orange_banner", "emerald_yellow_banner"],
        "jungle":  ["emerald_item_frame", "emerald_brown_banner", "emerald_green_banner", "emerald_lime_banner"],
        "plains":  ["emerald_item_frame", "emerald_white_banner", "emerald_brown_banner", "emerald_light_gray_banner"],
        "savanna": ["emerald_item_frame", "emerald_green_banner", "emerald_red_banner", "emerald_yellow_banner"],
        "snow":    ["emerald_item_frame", "emerald_white_banner", "emerald_blue_banner", "emerald_light_blue_banner"],
        "swamp":   ["emerald_item_frame", "emerald_black_banner", "emerald_purple_banner", "emerald_gray_banner"],
        "taiga":   ["emerald_item_frame", "emerald_blue_banner", "emerald_cyan_banner", "emerald_light_blue_banner"],
    },
    # Fisherman L5: boat type depends on villager biome variant
    # plains→oak, taiga/snow→spruce, desert/jungle→jungle, savanna→acacia, swamp→dark_oak
    ("fisherman", 5): {
        "plains":  ["5/pufferfish_emerald", "5/oak_boat_emerald"],
        "taiga":   ["5/pufferfish_emerald", "5/spruce_boat_emerald"],
        "snow":    ["5/pufferfish_emerald", "5/spruce_boat_emerald"],
        "desert":  ["5/pufferfish_emerald", "5/jungle_boat_emerald"],
        "jungle":  ["5/pufferfish_emerald", "5/jungle_boat_emerald"],
        "savanna": ["5/pufferfish_emerald", "5/acacia_boat_emerald"],
        "swamp":   ["5/pufferfish_emerald", "5/dark_oak_boat_emerald"],
    },
}


def filter_pool_by_variant(pool: list, profession: str, level: int, variant: Optional[str]) -> list:
    """Filter the trade pool by variant. Returns the filtered pool (or original if no variant needed)."""
    if variant is None:
        return list(pool)
    key = (profession, level)
    if key not in VARIANT_FILTERS:
        return list(pool)
    variant_map = VARIANT_FILTERS[key]
    if variant not in variant_map:
        return list(pool)  # unknown variant -> use full pool
    allowed = variant_map[variant]
    return [entry for entry in pool if any(entry.endswith(suffix) for suffix in allowed)]


# ============================================================
# Special RNG: suspicious stew effects (farmer L4)
# ============================================================
STEW_EFFECTS = [
    ("night_vision", 100),   # 夜视 5秒 (100 ticks = 5s)
    ("jump_boost", 160),     # 跳跃提升 8秒
    ("weakness", 140),       # 虚弱 7秒
    ("blindness", 120),      # 失明 6秒
    ("poison", 280),         # 中毒 14秒
    ("saturation", 140),     # 饱和 7秒
]

def simulate_stew_effect(rng: XoroshiroRandomSource) -> dict:
    """Simulate set_stew_effect for farmer L4 suspicious stew trade."""
    idx = rng.next_int(len(STEW_EFFECTS))
    effect_name, duration = STEW_EFFECTS[idx]
    return {"effect": effect_name, "duration_ticks": duration}


# ============================================================
# Special RNG: tipped arrow potions (fletcher L5)
# ============================================================
# All tradeable potions from #minecraft:tradeable_potions tag (26.1)
TRADEABLE_POTIONS = [
    "wind_charged", "oozing", "infested", "weaving",
    "night_vision", "long_night_vision",
    "invisibility", "long_invisibility",
    "fire_resistance", "long_fire_resistance",
    "leaping", "long_leaping", "strong_leaping",
    "slowness", "long_slowness", "strong_slowness",
    "turtle_master", "long_turtle_master", "strong_turtle_master",
    "swiftness", "long_swiftness", "strong_swiftness",
    "water_breathing", "long_water_breathing",
    "healing", "strong_healing",
    "harming", "strong_harming",
    "poison", "long_poison", "strong_poison",
    "regeneration", "long_regeneration", "strong_regeneration",
    "strength", "long_strength", "strong_strength",
    "weakness", "long_weakness",
    "slow_falling", "long_slow_falling",
]

def simulate_random_potion(rng: XoroshiroRandomSource) -> dict:
    """Simulate set_random_potion for fletcher L5 tipped arrow trade."""
    idx = rng.next_int(len(TRADEABLE_POTIONS))
    return {"potion": TRADEABLE_POTIONS[idx]}


# ============================================================
# Special RNG: dyed leather armor (leatherworker all levels)
# ============================================================
DYE_COLORS = [
    "white", "orange", "magenta", "light_blue",
    "yellow", "lime", "pink", "gray",
    "light_gray", "cyan", "purple", "blue",
    "brown", "green", "red", "black",
]

def simulate_random_dyes(rng: XoroshiroRandomSource) -> dict:
    """
    Simulate set_random_dyes for leatherworker dyed armor/horse armor.
    
    Two-step RNG:
    1. Binomial(n=2, p=0.75) to determine dye count (1-3)
    2. nextInt(16) for each dye color
    
    Returns list of selected dye colors.
    """
    # Step 1: Binomial(n=2, p=0.75) → 1 + successes
    # Each trial: success if nextFloat() < 0.75
    successes = 0
    for _ in range(2):
        if rng.next_float() < 0.75:
            successes += 1
    dye_count = 1 + successes  # 1-3 dyes
    
    # Step 2: Select each dye color
    dyes = []
    for _ in range(dye_count):
        dyes.append(DYE_COLORS[rng.next_int(16)])
    
    return {"dyes": dyes, "dye_count": dye_count}


# ============================================================
# Entry type detection helpers
# ============================================================
def is_suspicious_stew_entry(entry_name: str) -> bool:
    return "suspicious_stew" in entry_name

def is_tipped_arrow_entry(entry_name: str) -> bool:
    return "tipped_arrow" in entry_name

def is_dyed_equipment_entry(entry_name: str) -> bool:
    return "dyed_leather" in entry_name or "dyed_leather_horse_armor" in entry_name


# ============================================================
# Observation structure
# ============================================================
@dataclass
class TradeObservation:
    profession: str
    level: int
    enchantment: Optional[str] = None
    enchant_level: Optional[int] = None
    price: Optional[int] = None
    slot: Optional[int] = None
    is_enchanted_book: bool = False


# ============================================================
# Prediction Engine
# ============================================================
class VillagerTradePredictor:
    """
    Predicts villager trades based on world seed.

    Core approach:
    1. Given world seed + trade_set identifier -> derive Xoroshiro128++ state
    2. Simulate trade generation (addOffersFromItemListingsWithoutDuplicates)
    3. Match observations to find reroll offset
    4. Predict future trades at that offset
    """

    def __init__(self, world_seed: int, variant: Optional[str] = None,
                 game_version: str = DEFAULT_GAME_VERSION):
        self.world_seed = u64(world_seed)
        self.variant = variant  # villager variant (biome-based): desert/jungle/plains/savanna/snow/swamp/taiga
        if game_version not in GAME_VERSIONS:
            raise ValueError(f"Unknown game version: {game_version}")
        self.game_version = game_version

    def create_rng(self, profession: str, level: int) -> XoroshiroRandomSource:
        identifier = trade_set_id(profession, level)
        return XoroshiroRandomSource.from_world_seed_and_id(self.world_seed, identifier)

    def _get_filtered_pool(self, profession: str, level: int) -> Tuple[list, int, Optional[dict]]:
        """Get the variant-filtered trade pool for a profession/level."""
        data = ALL_TRADE_DATA.get(profession, {}).get(level, {})
        if not data:
            return [], 0, None
        raw_pool = apply_pool_order(list(data["pool"]), profession, level,
                                    self.game_version)
        amount = data["amount"]
        filtered_pool = filter_pool_by_variant(raw_pool, profession, level, self.variant)
        return filtered_pool, amount, data

    def simulate_trades(self, profession: str, level: int,
                        rng: Optional[XoroshiroRandomSource] = None) -> List[dict]:
        """
        Simulate trade generation matching MC 26.1's addOffersFromItemListingsWithoutDuplicates.
        
        Supports:
        - Variant filtering (merchant_predicate) for cartographer/shepherd/leatherworker
        - Special RNG: suspicious stew, tipped arrows, dyed leather
        - Enchanted books and equipment
        """
        if rng is None:
            rng = self.create_rng(profession, level)

        pool, amount, data = self._get_filtered_pool(profession, level)
        if not pool:
            return []

        offers = []
        offers_found = 0

        while offers_found < amount and pool:
            roll = rng.next_int(len(pool))
            picked = pool[roll]
            pool.pop(roll)

            offer = self._generate_offer(rng, picked)
            if offer is not None:
                offers.append(offer)
                offers_found += 1

        return offers

    def _generate_offer(self, rng: XoroshiroRandomSource, entry_name: str) -> Optional[dict]:
        """Generate a single offer, advancing RNG exactly as MC would."""
        if is_enchanted_book_entry(entry_name):
            book = simulate_enchanted_book(rng, include_additional_cost=True)
            return {"entry": entry_name, "type": "enchanted_book", **book}
        elif is_enchanted_equipment_entry(entry_name):
            params = ENCHANTED_EQUIPMENT_PARAMS.get(entry_name)
            if params:
                item_id, lmin, lmax, base_cost = params
                extra = WEAPON_AXE_ENCHANTS if "weaponsmith" in entry_name and "axe" in entry_name else None
                equip = simulate_enchanted_equipment(rng, item_id, lmin, lmax,
                                                     include_additional_cost=True, base_cost=base_cost,
                                                     compat_override=extra)
            else:
                equip = simulate_enchanted_equipment(rng, "minecraft:iron_sword", 5, 19, include_additional_cost=True)
            return {"entry": entry_name, **equip}
        elif is_suspicious_stew_entry(entry_name):
            stew = simulate_stew_effect(rng)
            return {"entry": entry_name, "type": "suspicious_stew", **stew}
        elif is_tipped_arrow_entry(entry_name):
            potion = simulate_random_potion(rng)
            return {"entry": entry_name, "type": "tipped_arrow", **potion}
        elif is_dyed_equipment_entry(entry_name):
            dyes = simulate_random_dyes(rng)
            return {"entry": entry_name, "type": "dyed_equipment", **dyes}
        else:
            return {"entry": entry_name, "type": "other"}

    def _consume_trade_generation(self, rng: XoroshiroRandomSource, profession: str, level: int):
        """Advance RNG by one complete trade generation (with variant filtering)."""
        pool, amount, data = self._get_filtered_pool(profession, level)
        if not pool:
            return

        offers_found = 0
        while offers_found < amount and pool:
            roll = rng.next_int(len(pool))
            picked = pool[roll]
            pool.pop(roll)

            if is_enchanted_book_entry(picked):
                simulate_enchanted_book(rng, include_additional_cost=True)
            elif is_enchanted_equipment_entry(picked):
                params = ENCHANTED_EQUIPMENT_PARAMS.get(picked)
                if params:
                    item_id, lmin, lmax, base_cost = params
                    extra = WEAPON_AXE_ENCHANTS if "weaponsmith" in picked and "axe" in picked else None
                    simulate_enchanted_equipment(rng, item_id, lmin, lmax,
                                                 include_additional_cost=True, base_cost=base_cost,
                                                 compat_override=extra)
                else:
                    simulate_enchanted_equipment(rng, "minecraft:iron_sword", 5, 19, include_additional_cost=True)
            elif is_suspicious_stew_entry(picked):
                simulate_stew_effect(rng)
            elif is_tipped_arrow_entry(picked):
                simulate_random_potion(rng)
            elif is_dyed_equipment_entry(picked):
                simulate_random_dyes(rng)
            offers_found += 1

    def find_offsets(self, profession: str, level: int,
                     observations: List[TradeObservation],
                     max_offset: int = 100) -> List[int]:
        """
        Find which reroll offsets match the observations.
        Each offset represents one complete trade generation that was consumed.
        """
        matching = []
        for offset in range(max_offset):
            rng = self.create_rng(profession, level)
            for _ in range(offset):
                self._consume_trade_generation(rng, profession, level)

            trades = self.simulate_trades(profession, level, rng)
            if self._matches(trades, observations):
                matching.append(offset)
                if len(matching) >= 10:
                    break
        return matching

    def predict_at_offset(self, profession: str, level: int, offset: int) -> List[dict]:
        """Predict trades at a specific reroll offset."""
        rng = self.create_rng(profession, level)
        for _ in range(offset):
            self._consume_trade_generation(rng, profession, level)
        return self.simulate_trades(profession, level, rng)

    def _matches(self, trades: List[dict], observations: List[TradeObservation]) -> bool:
        """Check if trades match all observations."""
        for obs in observations:
            found = False
            for t in trades:
                if obs.is_enchanted_book and t.get("type") == "enchanted_book":
                    if t.get("enchantment") == obs.enchantment:
                        if obs.enchant_level is None or t.get("level") == obs.enchant_level:
                            if obs.price is None or t.get("final_cost") == obs.price:
                                found = True
                                break
            if not found:
                return False
        return True

    def predict_all_levels(self, profession: str = "librarian") -> Dict[int, List[dict]]:
        """Predict trades for all levels of a profession."""
        result = {}
        for level in range(1, 6):
            result[level] = self.simulate_trades(profession, level)
        return result


# ============================================================
# Debug helpers
# ============================================================
def debug_seed_derivation(world_seed: int, profession: str, level: int):
    identifier = trade_set_id(profession, level)
    print(f"=== Seed Derivation for {identifier} ===")
    print(f"World seed:       {world_seed} (0x{u64(world_seed):016X})")
    effective = u64(world_seed ^ DEFAULT_SALT)
    print(f"Effective seed:   0x{effective:016X}")
    unmixed = upgrade_seed_to_128bit_unmixed(effective)
    print(f"Unmixed:          lo=0x{unmixed.lo:016X} hi=0x{unmixed.hi:016X}")
    key_hash = seed_from_hash_of(identifier)
    print(f"Key hash:         lo=0x{key_hash.lo:016X} hi=0x{key_hash.hi:016X}")
    xored = unmixed.xor_other(key_hash)
    print(f"After XOR:        lo=0x{xored.lo:016X} hi=0x{xored.hi:016X}")
    mixed = xored.mixed()
    print(f"Mixed:            lo=0x{mixed.lo:016X} hi=0x{mixed.hi:016X}")
    rng = Xoroshiro128PlusPlus(mixed.lo, mixed.hi)
    print(f"First nextInt values:")
    for i in range(8):
        print(f"  nextInt({3}) = {rng.next_int(3)}")
    return mixed


# ============================================================
# CLI Interface
# ============================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MC 26.1 Villager Trade Prediction System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Predict librarian trades for world seed 12345
  python villager_trade_predictor.py 12345

  # Predict with offset (after 3 rerolls)
  python villager_trade_predictor.py 12345 --offset 3

  # Find offset from observed enchantment
  python villager_trade_predictor.py 12345 -l 1 -o mending:1

  # Debug seed derivation
  python villager_trade_predictor.py 12345 --debug
        """)
    parser.add_argument("world_seed", type=lambda x: int(x, 0),
                        help="World seed (decimal or 0x hex)")
    parser.add_argument("--profession", "-p", default="librarian", choices=PROFESSIONS)
    parser.add_argument("--level", "-l", type=int, default=None,
                        help="Level 1-5, or omit for all")
    parser.add_argument("--offset", type=int, default=0,
                        help="Reroll offset (0=first roll)")
    parser.add_argument("--observe", "-o", nargs="+", default=None,
                        help="Observed: enchant_name[:level] (e.g. mending:1 efficiency:5)")
    parser.add_argument("--max-offset", type=int, default=100,
                        help="Max offset to search when observing (default: 100)")
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--compact", "-c", action="store_true",
                        help="Compact output (only enchanted books)")

    args = parser.parse_args()
    predictor = VillagerTradePredictor(args.world_seed)

    if args.debug:
        if args.level:
            debug_seed_derivation(args.world_seed, args.profession, args.level)
        else:
            for lv in range(1, 6):
                debug_seed_derivation(args.world_seed, args.profession, lv)
                print()

    if args.observe:
        # Search mode: find offset from observations
        observations = []
        for obs_str in args.observe:
            parts = obs_str.split(":")
            observations.append(TradeObservation(
                profession=args.profession,
                level=args.level or 1,
                enchantment=parts[0],
                enchant_level=int(parts[1]) if len(parts) > 1 else None,
                is_enchanted_book=True,
            ))

        target_level = args.level or 1
        print(f"Searching for matching offsets for {args.profession} level {target_level}...")
        print(f"Observations: {[(o.enchantment, o.enchant_level) for o in observations]}")

        offsets = predictor.find_offsets(args.profession, target_level, observations, args.max_offset)

        if offsets:
            print(f"\nMatching offsets: {offsets}")
            for off in offsets[:5]:
                print(f"\n  Offset {off}:")
                trades = predictor.predict_at_offset(args.profession, target_level, off)
                for t in trades:
                    if t.get("type") == "enchanted_book":
                        print(f"    {t['enchantment']} {t['level']} ({t['final_cost']} emeralds)"
                              f"{' [treasure]' if t['is_treasure'] else ''}")
                    elif not args.compact:
                        print(f"    [{t['type']}] {t['entry'].split('/')[-1]}")
        else:
            print("No matching offsets found. Check observations and world seed.")
    else:
        # Prediction mode
        levels = [args.level] if args.level else [1, 2, 3, 4, 5]
        offset = args.offset

        print(f"\nPredicted trades for {args.profession} (seed={args.world_seed}, offset={offset})")
        print("=" * 60)

        for level in levels:
            trades = predictor.predict_at_offset(args.profession, level, offset)
            print(f"\n  Level {level}:")
            for t in trades:
                if t.get("type") == "enchanted_book":
                    print(f"    {t['enchantment']} {t['level']} ({t['final_cost']} emeralds)"
                          f"{' [treasure]' if t['is_treasure'] else ''}")
                elif t.get("type") == "enchanted_equipment":
                    item = t.get("item", "unknown").replace("minecraft:", "")
                    cost = t.get("final_cost", "?")
                    print(f"    enchanted {item} (+{cost} emeralds)")
                elif not args.compact:
                    name = t["entry"].split("/")[-1]
                    print(f"    {name}")


if __name__ == "__main__":
    main()
