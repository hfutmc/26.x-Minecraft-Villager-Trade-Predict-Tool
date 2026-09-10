"""
村民交易导出工具 - GUI界面
导出指定职业、等级、偏移节点的后续交易为CSV
含节点定位（观测反查偏移）和预览表筛选功能
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import json
import os
from datetime import datetime

from villager_trade_predictor import (
    VillagerTradePredictor, ALL_TRADE_DATA,
    TRADEABLE_ENCHANTMENTS, DOUBLE_PRICE_SET,
    is_enchanted_book_entry, is_enchanted_equipment_entry,
    is_suspicious_stew_entry, is_tipped_arrow_entry,
    is_dyed_equipment_entry, ENCHANTED_EQUIPMENT_PARAMS,
    ITEM_ENCHANTMENT_COMPAT, ON_TRADED_EQUIPMENT_ENCHANTMENTS,
    NON_TREASURE_ENCHANTMENTS,
    filter_pool_by_variant,
)

# ============================================================
# 附魔冲突组（互斥附魔，勾选一个时自动取消同组其他勾选）
# ============================================================
ENCHANTMENT_CONFLICT_GROUPS = [
    # 盔甲保护（四选一）
    {"protection", "fire_protection", "blast_protection", "projectile_protection"},
    # 剑类伤害（三选一）
    {"sharpness", "smite", "bane_of_arthropods"},
    # 工具（二选一）
    {"fortune", "silk_touch"},
    # 弩（二选一）
    {"multishot", "piercing"},
    # 三叉戟（激流与忠诚、引雷互斥）
    {"riptide", "channeling"},
    {"riptide", "loyalty"},
    # 重锤（二选一）
    {"density", "breach"},
]

CONFIG_FILE = "export_trades_config.json"

# ============================================================
# 中文对照
# ============================================================
PROFESSION_CN = {
    "armorer": "盔甲匠", "butcher": "屠夫", "cartographer": "制图师",
    "cleric": "牧师", "farmer": "农民", "fisherman": "渔夫",
    "fletcher": "制箭师", "leatherworker": "皮匠", "librarian": "图书管理员",
    "mason": "石匠", "shepherd": "牧羊人", "toolsmith": "工具匠",
    "weaponsmith": "武器匠",
}
PROFESSION_EN = {v: k for k, v in PROFESSION_CN.items()}

ENCHANTMENT_CN = {
    "protection": "保护", "fire_protection": "火焰保护", "feather_falling": "摔落保护",
    "blast_protection": "爆炸保护", "projectile_protection": "弹射物保护",
    "respiration": "水下呼吸", "aqua_affinity": "水下速掘", "thorns": "荆棘",
    "depth_strider": "深海探索者", "sharpness": "锋利", "smite": "亡灵杀手",
    "bane_of_arthropods": "节肢杀手", "knockback": "击退", "fire_aspect": "火焰附加",
    "looting": "抢夺", "sweeping_edge": "横扫之刃", "efficiency": "效率",
    "silk_touch": "精准采集", "unbreaking": "耐久", "fortune": "时运",
    "power": "力量", "punch": "冲击", "flame": "火矢", "infinity": "无限",
    "luck_of_the_sea": "海之眷顾", "lure": "饵钓", "loyalty": "忠诚",
    "impaling": "穿刺", "riptide": "激流", "channeling": "引雷",
    "multishot": "多重射击", "quick_charge": "快速装填", "piercing": "穿透",
    "density": "致密", "breach": "破甲", "lunge": "突进",
    "binding_curse": "绑定诅咒", "vanishing_curse": "消失诅咒",
    "swift_sneak": "迅捷潜行", "soul_speed": "灵魂疾行",
    "frost_walker": "冰霜行者", "mending": "经验修补", "wind_burst": "风爆",
}
ENCHANTMENT_EN = {v: k for k, v in ENCHANTMENT_CN.items()}

LEVEL_NAMES = {1: "新手", 2: "学徒", 3: "老手", 4: "专家", 5: "大师"}

STEW_CN = {
    "night_vision": "夜视", "jump_boost": "跳跃提升", "weakness": "虚弱",
    "blindness": "失明", "poison": "中毒", "saturation": "饱和",
}
STEW_EN = {v: k for k, v in STEW_CN.items()}

POTION_CN = {
    "wind_charged": "风弹", "oozing": "渗浆", "infested": "虫蚀", "weaving": "织网",
    "night_vision": "夜视", "long_night_vision": "夜视(延长)",
    "invisibility": "隐身", "long_invisibility": "隐身(延长)",
    "fire_resistance": "抗火", "long_fire_resistance": "抗火(延长)",
    "leaping": "跳跃", "long_leaping": "跳跃(延长)", "strong_leaping": "跳跃II",
    "slowness": "迟缓", "long_slowness": "迟缓(延长)", "strong_slowness": "迟缓IV",
    "turtle_master": "神龟", "long_turtle_master": "神龟(延长)", "strong_turtle_master": "神龟II",
    "swiftness": "迅捷", "long_swiftness": "迅捷(延长)", "strong_swiftness": "迅捷II",
    "water_breathing": "水肺", "long_water_breathing": "水肺(延长)",
    "healing": "治疗", "strong_healing": "治疗II",
    "harming": "伤害", "strong_harming": "伤害II",
    "long_poison": "剧毒(延长)", "strong_poison": "剧毒II",
    "regeneration": "再生", "long_regeneration": "再生(延长)", "strong_regeneration": "再生II",
    "strength": "力量", "long_strength": "力量(延长)", "strong_strength": "力量II",
    "weakness": "虚弱", "long_weakness": "虚弱(延长)",
    "slow_falling": "缓降", "long_slow_falling": "缓降(延长)",
}
POTION_EN = {v: k for k, v in POTION_CN.items()}

DYE_CN = {
    "white": "白", "orange": "橙", "magenta": "品红", "light_blue": "淡蓝",
    "yellow": "黄", "lime": "黄绿", "pink": "粉", "gray": "灰",
    "light_gray": "淡灰", "cyan": "青", "purple": "紫", "blue": "蓝",
    "brown": "棕", "green": "绿", "red": "红", "black": "黑",
}

TRADE_TYPE_CN = ["附魔书", "附魔装备", "迷之炖菜", "药箭", "染色装备", "普通交易"]

# ============================================================
# 交易池条目解析
# ============================================================
def parse_pool_entry(entry: str) -> dict:
    """将池中的一个条目解析为 {label, type, type_cn, data}。
    
    使用与 predictor 完全相同的检测逻辑。所有池条目都是字符串格式。"""
    suffix = entry.rsplit("/", 1)[-1]

    if is_enchanted_book_entry(entry):
        return {"label": "附魔书", "type": "enchanted_book", "type_cn": "附魔书", "data": {"entry": entry}}
    elif is_enchanted_equipment_entry(entry):
        params = ENCHANTED_EQUIPMENT_PARAMS.get(entry)
        if params:
            item_name = params[0].replace("minecraft:", "")
            return {"label": f"附魔装备 ({item_name})", "type": "enchanted_equipment",
                    "type_cn": "附魔装备", "data": {"entry": entry, "item": params[0],
                                                    "levels_min": params[1], "levels_max": params[2]}}
        return {"label": f"附魔装备 ({suffix})", "type": "enchanted_equipment",
                "type_cn": "附魔装备", "data": {"entry": entry}}
    elif is_suspicious_stew_entry(entry):
        return {"label": "迷之炖菜", "type": "suspicious_stew", "type_cn": "迷之炖菜",
                "data": {"entry": entry}}
    elif is_tipped_arrow_entry(entry):
        return {"label": "药箭", "type": "tipped_arrow", "type_cn": "药箭",
                "data": {"entry": entry}}
    elif is_dyed_equipment_entry(entry):
        item_hint = "leather_horse_armor" if "horse" in suffix else "leather_armor"
        return {"label": f"染色装备 ({item_hint})", "type": "dyed_equipment",
                "type_cn": "染色装备", "data": {"entry": entry}}
    else:
        return {"label": suffix, "type": "other", "type_cn": "普通交易",
                "data": {"entry": entry}}


def get_pool_entry_list(prof: str, level: int, variant: str | None = None) -> list[dict]:
    """获取某职业等级的池条目列表（含类型信息）。"""
    data = ALL_TRADE_DATA.get(prof, {}).get(level, {})
    if not data or "pool" not in data:
        return []

    pool = data["pool"]
    # 应用variant过滤（制图师、牧羊人、皮匠、渔夫）
    pool = filter_pool_by_variant(list(pool), prof, level, variant)

    return [parse_pool_entry(e) for e in pool]


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_seed": "", "history": [], "last_prof": "图书管理员", "last_level": "1-新手"}


def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def translate_trade(t: dict) -> str:
    tp = t.get("type", "other")
    if tp == "enchanted_book":
        ench_cn = ENCHANTMENT_CN.get(t["enchantment"], t["enchantment"])
        treasure = " [宝藏]" if t.get("is_treasure") else ""
        return f"附魔书: {ench_cn} {t['level']} ({t['final_cost']}E){treasure}"
    elif tp == "enchanted_equipment":
        item = t.get("item", "?").replace("minecraft:", "")
        enchs = ", ".join(f"{ENCHANTMENT_CN.get(n, n)} {lv}" for n, lv in t.get("enchantments", []))
        return f"附魔装备: {item} [{enchs}] ({t.get('final_cost', '?')}E)"
    elif tp == "suspicious_stew":
        eff = STEW_CN.get(t.get("effect", "?"), t.get("effect", "?"))
        dur = t.get("duration_ticks", 0) / 20
        return f"迷之炖菜: {eff} ({dur:.0f}秒)"
    elif tp == "tipped_arrow":
        pot = POTION_CN.get(t.get("potion", "?"), t.get("potion", "?"))
        return f"药箭: {pot}"
    elif tp == "dyed_equipment":
        dyes = ", ".join(DYE_CN.get(d, d) for d in t.get("dyes", []))
        return f"染色装备: {dyes}"
    else:
        return t.get("entry", "?").rsplit("/", 1)[-1].replace("_", " ")


def trade_to_csv_row(t: dict, offset: int, level: int) -> list:
    tp = t.get("type", "other")
    if tp == "enchanted_book":
        return [
            offset, level,
            t.get("entry", "").rsplit("/", 1)[-1],
            "附魔书", ENCHANTMENT_CN.get(t["enchantment"], t["enchantment"]),
            t["enchantment"], t["level"], t["final_cost"],
            "是" if t.get("is_treasure") else "否",
        ]
    elif tp == "enchanted_equipment":
        item = t.get("item", "?").replace("minecraft:", "")
        enchs = "; ".join(f"{ENCHANTMENT_CN.get(n, n)} {lv}" for n, lv in t.get("enchantments", []))
        return [
            offset, level,
            t.get("entry", "").rsplit("/", 1)[-1],
            "附魔装备", item, enchs, "", t.get("final_cost", ""),
            "",
        ]
    elif tp == "suspicious_stew":
        eff = STEW_CN.get(t.get("effect", "?"), t.get("effect", "?"))
        return [
            offset, level,
            t.get("entry", "").rsplit("/", 1)[-1],
            "迷之炖菜", eff, str(t.get("duration_ticks", 0) / 20) + "秒",
            "", "", "",
        ]
    elif tp == "tipped_arrow":
        pot = POTION_CN.get(t.get("potion", "?"), t.get("potion", "?"))
        return [
            offset, level,
            t.get("entry", "").rsplit("/", 1)[-1],
            "药箭", pot, "", "", "", "",
        ]
    elif tp == "dyed_equipment":
        dyes = "/".join(DYE_CN.get(d, d) for d in t.get("dyes", []))
        return [
            offset, level,
            t.get("entry", "").rsplit("/", 1)[-1],
            "染色装备", dyes, str(t.get("dye_count", "")),
            "", "", "",
        ]
    else:
        return [
            offset, level,
            t.get("entry", "").rsplit("/", 1)[-1],
            "普通", "", "", "", "", "",
        ]


# ============================================================
# 附魔选择弹窗
# ============================================================
class EnchantmentSelector(tk.Toplevel):
    def __init__(self, parent, title="选择附魔"):
        super().__init__(parent)
        self.title(title)
        self.geometry("420x480")
        self.resizable(False, False)
        self.result = None
        self._selected_data = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text="搜索:").pack(padx=5, pady=(10, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._filter())
        ttk.Entry(self, textvariable=self.search_var, width=40).pack(padx=5)

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        # Keep the enchantment selected while the user operates the level
        # combobox. With exportselection=True, the combobox can clear it.
        self.listbox = tk.Listbox(
            list_frame, height=14, font=("Microsoft YaHei", 10),
            exportselection=False,
        )
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", lambda e: self._confirm())
        self.listbox.bind("<ButtonRelease-1>", self._on_list_select)

        level_frame = ttk.Frame(self)
        level_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(level_frame, text="等级:").pack(side="left")
        self.level_var = tk.StringVar()
        self.level_combo = ttk.Combobox(level_frame, textvariable=self.level_var,
                                        values=[], width=6, state="readonly")
        self.level_combo.pack(side="left", padx=5)
        self.level_combo.bind("<<ComboboxSelected>>", self._on_level)

        self.price_label = ttk.Label(level_frame, text="")
        self.price_label.pack(side="left", padx=10)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=10)
        ttk.Button(btn_frame, text="确定", command=self._confirm).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="取消", command=self._cancel).pack(side="right")

        self._populate()

    def _populate(self):
        self.all_data = []
        for name, max_lv in TRADEABLE_ENCHANTMENTS:
            cn = ENCHANTMENT_CN.get(name, name)
            treasure = " [宝藏]" if name in DOUBLE_PRICE_SET else ""
            self.all_data.append((name, max_lv, cn, treasure))
        self._filter()

    def _filter(self):
        s = self.search_var.get().lower().strip()
        self._selected_data = None
        self.listbox.delete(0, "end")
        self.listbox._idx_map = {}
        for name, max_lv, cn, treasure in self.all_data:
            if s in cn or s in name:
                idx = self.listbox.size()
                self.listbox.insert("end", f"{cn} (1-{max_lv}){treasure}")
                self.listbox._idx_map[idx] = (name, max_lv)

    def _on_list_select(self, event=None):
        """当列表选中项变化时，更新等级下拉框的可选值。"""
        sel = self.listbox.curselection()
        if not sel:
            self.level_combo["values"] = []
            self.level_var.set("")
            return
        data = self.listbox._idx_map.get(sel[0])
        if not data:
            return
        self._selected_data = data
        name, max_lv = data
        levels = [str(i) for i in range(1, max_lv + 1)]
        self.level_combo["values"] = levels
        self.level_var.set(levels[0])
        self._on_level()

    def _on_level(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        data = self.listbox._idx_map.get(sel[0])
        if not data:
            return
        name, max_lv = data
        try:
            lv = int(self.level_var.get())
        except ValueError:
            return
        is_treasure = name in DOUBLE_PRICE_SET
        base_min = 2 + 3 * lv
        base_max = 6 + 13 * lv
        if is_treasure:
            base_min *= 2
            base_max *= 2
        self.price_label.config(text=f"价格: {base_min}~{base_max}")

    def _confirm(self):
        sel = self.listbox.curselection()
        data = self.listbox._idx_map.get(sel[0]) if sel else self._selected_data
        if not data:
            messagebox.showwarning("提示", "请先选择一个附魔", parent=self)
            return
        try:
            lv = int(self.level_var.get())
        except ValueError:
            messagebox.showwarning("提示", "请选择附魔等级", parent=self)
            return
        self.result = (data[0], lv)
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ============================================================
# 附魔装备选择弹窗（穿梭框）
# ============================================================
class EquipmentEnchantSelector(tk.Toplevel):
    """附魔装备专用的附魔选择弹窗，复选框交互，每项直接显示等级下拉框。"""
    def __init__(self, parent, equipment_item: str, levels_min: int = 5, levels_max: int = 19,
                 title="选择装备附魔"):
        super().__init__(parent)
        self.title(title)
        self.geometry("380x480")
        self.resizable(False, False)
        self.result = None          # list of (enchantment_name, level) tuples
        self.transient(parent)
        self.grab_set()

        self.equipment_item = equipment_item
        self.levels_min = levels_min
        self.levels_max = levels_max
        compat_set = ITEM_ENCHANTMENT_COMPAT.get(equipment_item, set())
        self._max_level_map = {name: max_lv for name, max_lv in ON_TRADED_EQUIPMENT_ENCHANTMENTS}

        # Filter: only compatible enchants that are in ON_TRADED_EQUIPMENT_ENCHANTMENTS
        self._available_enchants = []
        for name, max_lv in ON_TRADED_EQUIPMENT_ENCHANTMENTS:
            if name in compat_set:
                cn = ENCHANTMENT_CN.get(name, name)
                self._available_enchants.append((name, max_lv, cn))

        # — 提示标签 —
        ttk.Label(self, text=f"装备: {equipment_item.replace('minecraft:', '')}",
                  font=("", 9, "bold")).pack(pady=(8, 2))
        ttk.Label(self, text=f"附魔等级约束: {levels_min}~{levels_max}级  |  勾选附魔并选择等级",
                  foreground="gray", font=("", 8)).pack()

        # — 可滚动附魔列表 —
        list_container = ttk.Frame(self)
        list_container.pack(fill="both", expand=True, padx=10, pady=5)

        self._list_canvas = tk.Canvas(list_container, width=340)
        self._list_scrollbar = ttk.Scrollbar(list_container, orient="vertical",
                                              command=self._list_canvas.yview)
        self._list_inner = ttk.Frame(self._list_canvas)
        self._list_inner.bind("<Configure>",
                              lambda e: self._list_canvas.configure(
                                  scrollregion=self._list_canvas.bbox("all")))
        self._list_window = self._list_canvas.create_window((0, 0), window=self._list_inner, anchor="nw")
        self._list_canvas.configure(yscrollcommand=self._list_scrollbar.set)
        self._list_canvas.pack(side="left", fill="both", expand=True)
        self._list_scrollbar.pack(side="right", fill="y")
        self._list_canvas.bind("<Configure>", lambda e: self._list_canvas.itemconfig(
            self._list_window, width=e.width))

        # 为每个兼容附魔创建一行: [复选框] [名称] [等级下拉框]
        self._check_vars = {}   # name -> tk.BooleanVar
        self._level_vars = {}   # name -> tk.StringVar
        self._level_combos = {} # name -> ttk.Combobox

        for name, max_lv, cn in self._available_enchants:
            row = ttk.Frame(self._list_inner)
            row.pack(fill="x", pady=1)

            chk_var = tk.BooleanVar(value=False)
            self._check_vars[name] = chk_var
            cb = ttk.Checkbutton(row, variable=chk_var,
                                 command=lambda n=name: self._on_check(n))
            cb.pack(side="left", padx=2)

            ttk.Label(row, text=f"{cn} (1-{max_lv})", width=16, anchor="w").pack(side="left", padx=2)

            lv_var = tk.StringVar(value="1")
            self._level_vars[name] = lv_var
            lv_combo = ttk.Combobox(row, textvariable=lv_var,
                                     values=[str(i) for i in range(1, max_lv + 1)],
                                     width=4, state="disabled")
            lv_combo.pack(side="left", padx=2)
            lv_combo.bind("<<ComboboxSelected>>", lambda e: self._update_equiv_level())
            self._level_combos[name] = lv_combo

        # — 底部：等同等级 + 按钮 —
        self._equiv_label = ttk.Label(self, text="等同附魔等级: --", foreground="gray", font=("", 8))
        self._equiv_label.pack(pady=2)

        btn_frame2 = ttk.Frame(self)
        btn_frame2.pack(fill="x", pady=10)
        ttk.Button(btn_frame2, text="确定", command=self._confirm).pack(side="right", padx=10)
        ttk.Button(btn_frame2, text="取消", command=self._cancel).pack(side="right")

        self._update_equiv_level()

    def _on_check(self, name: str):
        """复选框切换时启用/禁用对应等级下拉框，并处理附魔冲突。"""
        checked = self._check_vars[name].get()
        combo = self._level_combos[name]
        if checked:
            combo.configure(state="readonly")
            # 自动取消同组冲突附魔的勾选
            for group in ENCHANTMENT_CONFLICT_GROUPS:
                if name in group:
                    for conflicting in group:
                        if conflicting != name and conflicting in self._check_vars:
                            if self._check_vars[conflicting].get():
                                self._check_vars[conflicting].set(False)
                                self._level_combos[conflicting].configure(state="disabled")
                    break
        else:
            combo.configure(state="disabled")
        self._update_equiv_level()

    def _update_equiv_level(self):
        """更新等同附魔等级显示——基于已勾选附魔中门槛最高的最低附魔能力。"""
        max_min = 0
        for name, chk_var in self._check_vars.items():
            if not chk_var.get():
                continue
            try:
                lv = int(self._level_vars[name].get())
            except ValueError:
                lv = 1
            min_enchant = 1 + 10 * (lv - 1)
            if min_enchant > max_min:
                max_min = min_enchant
        if max_min == 0:
            self._equiv_label.config(text="等同附魔等级: -- (未勾选)")
        else:
            self._equiv_label.config(
                text=f"等同附魔等级: {max_min} (约束: {self.levels_min}~{self.levels_max}级)")

    def _confirm(self):
        from tkinter import messagebox
        selected = []
        for name, chk_var in self._check_vars.items():
            if not chk_var.get():
                continue
            try:
                lv = int(self._level_vars[name].get())
            except ValueError:
                lv = 1
            max_lv = self._max_level_map.get(name, 5)
            if lv < 1 or lv > max_lv:
                cn = ENCHANTMENT_CN.get(name, name)
                messagebox.showwarning("提示", f"{cn} 等级必须在 1~{max_lv} 之间", parent=self)
                return
            selected.append((name, lv))

        if not selected:
            messagebox.showwarning("提示", "请至少勾选一个附魔", parent=self)
            return

        self.result = selected
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ============================================================
# 主窗口
# ============================================================
class TradeExportApp:
    def __init__(self, root):
        self.root = root
        self.root.title("村民交易导出工具 - MC 26.1")
        self.root.geometry("1100x900")
        self.root.minsize(900, 700)

        self.predictor = None
        self.config = load_config()
        self.current_data = []
        self.filtered_data = []
        self.observations = []
        self._pool_entries = []      # 当前职业等级的池条目缓存
        self._slot_combo_vars = []   # 各槽位的 Combobox StringVar
        self._slot_combo_widgets = []  # 各槽位的 Combobox 控件
        self._slot_detail_frames = []  # 各槽位的详情 Frame
        self._slot_enchants = {}     # {slot_idx: (ench, lv)}  or for equipment: [(name, lv), ...]
        self._slot_entry_indices = {}  # {slot_idx: pool_entry_idx} 
        
        self._build_ui()

    # ============================================================
    # UI 构建
    # ============================================================
    def _build_ui(self):
        # ── 第一行：种子 + 职业 + 等级 + 群系 ──
        frame_seed = ttk.LabelFrame(self.root, text="基本设置", padding=10)
        frame_seed.pack(fill="x", padx=10, pady=5)

        # 子行1：种子
        row1 = ttk.Frame(frame_seed)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="世界种子:").pack(side="left")
        self.seed_var = tk.StringVar(value=self.config.get("last_seed", ""))
        ttk.Entry(row1, textvariable=self.seed_var, width=28).pack(side="left", padx=5)

        history = self.config.get("history", [])
        if history:
            ttk.Label(row1, text="历史:").pack(side="left", padx=(10, 0))
            self.seed_history_var = tk.StringVar()
            seed_history = ttk.Combobox(
                row1, textvariable=self.seed_history_var,
                values=history, width=25, state="readonly"
            )
            seed_history.pack(side="left", padx=5)
            seed_history.bind("<<ComboboxSelected>>", lambda e: self.seed_var.set(self.seed_history_var.get()))

        ttk.Button(row1, text="加载种子", command=self._load_seed).pack(side="left", padx=10)
        self.seed_status = ttk.Label(row1, text="", foreground="gray")
        self.seed_status.pack(side="left", padx=10)

        # 子行2：职业 + 等级 + 群系
        row2 = ttk.Frame(frame_seed)
        row2.pack(fill="x", pady=2)

        ttk.Label(row2, text="职业:").pack(side="left")
        self.prof_var = tk.StringVar(value=self.config.get("last_prof", "图书管理员"))
        self.prof_combo = ttk.Combobox(
            row2, textvariable=self.prof_var,
            values=list(PROFESSION_CN.values()),
            width=14, state="readonly"
        )
        self.prof_combo.pack(side="left", padx=5)
        self.prof_combo.bind("<<ComboboxSelected>>", self._on_prof_change)

        ttk.Label(row2, text="等级:").pack(side="left", padx=(10, 0))
        self.level_var = tk.StringVar(value=self.config.get("last_level", "1-新手"))
        self.level_combo = ttk.Combobox(
            row2, textvariable=self.level_var,
            values=[f"{i}-{LEVEL_NAMES[i]}" for i in range(1, 6)],
            width=10, state="readonly"
        )
        self.level_combo.pack(side="left", padx=5)
        self.level_combo.bind("<<ComboboxSelected>>", self._on_level_change)

        ttk.Label(row2, text="群系变体:").pack(side="left", padx=(10, 0))
        self.variant_var = tk.StringVar(value="默认(不过滤)")
        self.variant_combo = ttk.Combobox(
            row2, textvariable=self.variant_var,
            values=["默认(不过滤)", "desert-沙漠", "jungle-丛林", "plains-平原",
                    "savanna-热带草原", "snow-雪地", "swamp-沼泽", "taiga-针叶林"],
            width=16, state="readonly"
        )
        self.variant_combo.pack(side="left", padx=5)

        # ── 节点定位：观测反查 ──
        # 折叠/展开切换按钮
        self._locate_collapsed = False
        self._locate_toggle_btn = ttk.Button(self.root, text="▽ 节点定位",
                                              command=self._toggle_locate_panel)
        self._locate_toggle_btn.pack(fill="x", padx=10, pady=(5, 0))

        self.frame_locate = ttk.LabelFrame(self.root, text="节点定位（通过观测交易反查偏移）", padding=10)
        self.frame_locate.pack(fill="x", padx=10, pady=(0, 5))

        # 多槽位输入区：每个槽位一行（条目 + 详情），按游戏内顺序排列
        ttk.Label(self.frame_locate, text="填写本等级的所有交易槽位；多次观测请按刷新先后顺序添加：",
                  foreground="gray", font=("", 8)).pack(anchor="w")
        self.locate_slots_frame = ttk.Frame(self.frame_locate)
        self.locate_slots_frame.pack(fill="x", pady=2)

        # 操作行
        loc_row2 = ttk.Frame(self.frame_locate)
        loc_row2.pack(fill="x", pady=5)
        ttk.Button(loc_row2, text="+ 添加观测", command=self._add_observation).pack(side="left", padx=5)
        ttk.Button(loc_row2, text="删除选中", command=self._remove_observation).pack(side="left", padx=5)
        ttk.Button(loc_row2, text="清空观测", command=self._clear_observations).pack(side="left", padx=5)

        ttk.Label(loc_row2, text="搜索范围:").pack(side="left", padx=(20, 0))
        self.locate_range_var = tk.StringVar(value="2000")
        ttk.Entry(loc_row2, textvariable=self.locate_range_var, width=8).pack(side="left", padx=5)

        ttk.Button(loc_row2, text="开始定位", command=self._do_locate).pack(side="left", padx=10)
        ttk.Button(loc_row2, text="如果匹配数>1，继续搜索",
                   command=self._locate_continue).pack(side="left", padx=5)

        # 观测列表 + 定位结果
        loc_row3 = ttk.Frame(self.frame_locate)
        loc_row3.pack(fill="both", expand=True, pady=2)
        obs_list_frame = ttk.LabelFrame(loc_row3, text="已添加观测", padding=3)
        obs_list_frame.pack(side="left", fill="both", expand=True)
        self.obs_listbox = tk.Listbox(obs_list_frame, height=3, font=("Microsoft YaHei", 9))
        self.obs_listbox.pack(side="left", fill="both", expand=True)

        locate_result_frame = ttk.LabelFrame(loc_row3, text="定位结果", padding=3)
        locate_result_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        self.locate_result_list = tk.Listbox(locate_result_frame, height=3, font=("Microsoft YaHei", 9))
        self.locate_result_list.pack(fill="both", expand=True)
        self.locate_result_list.bind("<Double-Button-1>", self._on_locate_result_click)
        self.locate_status = ttk.Label(locate_result_frame, text="", foreground="gray")
        self.locate_status.pack()

        # ── 导出参数 ──
        frame_params = ttk.LabelFrame(self.root, text="导出参数", padding=10)
        frame_params.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_params, text="起始偏移:").pack(side="left")
        self.offset_var = tk.StringVar(value="0")
        ttk.Entry(frame_params, textvariable=self.offset_var, width=10).pack(side="left", padx=5)
        ttk.Label(frame_params, text="(重新放置次数)", foreground="gray", font=("", 8)).pack(side="left", padx=5)

        ttk.Separator(frame_params, orient="vertical").pack(side="left", fill="y", padx=15, pady=2)

        ttk.Label(frame_params, text="导出数量:").pack(side="left")
        self.count_var = tk.StringVar(value="100")
        ttk.Entry(frame_params, textvariable=self.count_var, width=10).pack(side="left", padx=5)
        ttk.Label(frame_params, text="(后续N个节点)", foreground="gray", font=("", 8)).pack(side="left", padx=5)

        # ── 操作按钮 ──
        frame_actions = ttk.Frame(self.root)
        frame_actions.pack(fill="x", padx=10, pady=5)
        ttk.Button(frame_actions, text="预览交易", command=self._preview).pack(side="left", padx=5)
        ttk.Button(frame_actions, text="导出CSV", command=self._export_csv).pack(side="left", padx=5)
        self.export_status = ttk.Label(frame_actions, text="", foreground="green")
        self.export_status.pack(side="left", padx=10)

        # ── 筛选栏（规则式：正反选 + OR连接，选项从数据动态填充）──
        frame_filter = ttk.LabelFrame(self.root, text="预览表筛选", padding=5)
        frame_filter.pack(fill="x", padx=10, pady=5)

        # 规则容器
        self.filter_rules_frame = ttk.Frame(frame_filter)
        self.filter_rules_frame.pack(fill="x", pady=1)

        # 操作行
        filter_ctrl = ttk.Frame(frame_filter)
        filter_ctrl.pack(fill="x", pady=2)
        ttk.Button(filter_ctrl, text="+ 添加规则", command=self._add_filter_rule).pack(side="left", padx=3)
        ttk.Button(filter_ctrl, text="清除全部", command=self._clear_filter).pack(side="left", padx=3)
        self.filter_status = ttk.Label(filter_ctrl, text="", foreground="gray")
        self.filter_status.pack(side="left", padx=10)

        # 规则列表(数据)：[{mode: "包含"|"排除", widgets: {...}}]
        self.filter_rules = []
        # 用于动态填充下拉的选项缓存
        self._filter_type_vals = ["全部"]
        self._filter_ench_vals = ["全部"]
        self._filter_lv_vals = ["任意"]
        self._filter_price_vals = ["全部价格"]

        # ── 结果预览区 ──
        frame_result = ttk.LabelFrame(self.root, text="交易预览 / 导出结果", padding=5)
        frame_result.pack(fill="both", expand=True, padx=10, pady=5)

        columns = ("offset", "level", "entry", "type", "detail1", "detail2", "ench_level", "price", "treasure")
        self.tree = ttk.Treeview(frame_result, columns=columns, show="headings", height=18)
        self.tree.heading("offset", text="偏移", command=lambda: self._sort_by("offset"))
        self.tree.heading("level", text="等级")
        self.tree.heading("entry", text="交易条目")
        self.tree.heading("type", text="类型")
        self.tree.heading("detail1", text="详情1")
        self.tree.heading("detail2", text="详情2")
        self.tree.heading("ench_level", text="附魔等级")
        self.tree.heading("price", text="价格(E)")
        self.tree.heading("treasure", text="宝藏")
        self.tree.column("offset", width=60, anchor="center")
        self.tree.column("level", width=50, anchor="center")
        self.tree.column("entry", width=200)
        self.tree.column("type", width=80, anchor="center")
        self.tree.column("detail1", width=120)
        self.tree.column("detail2", width=80)
        self.tree.column("ench_level", width=65, anchor="center")
        self.tree.column("price", width=65, anchor="center")
        self.tree.column("treasure", width=45, anchor="center")

        scrollbar = ttk.Scrollbar(frame_result, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 初始化池条目列表
        self._refresh_pool_entries()

    # ============================================================
    # 多槽位输入构建 + 池条目刷新
    # ============================================================
    def _refresh_pool_entries(self):
        """根据当前职业/等级/群系刷新所有槽位条目下拉框。"""
        prof = self._get_profession_en()
        level = self._get_level()
        self._pool_entries = get_pool_entry_list(prof, level, self._get_variant())
        all_labels = [e["label"] for e in self._pool_entries]

        data = ALL_TRADE_DATA.get(prof, {}).get(level, {})
        pool_size = len(self._pool_entries)
        amount = min(data.get("amount", 2), pool_size)

        # 重建槽位控件
        for w in self.locate_slots_frame.winfo_children():
            w.destroy()
        self._slot_combo_vars.clear()
        self._slot_combo_widgets.clear()
        self._slot_detail_frames.clear()
        self._slot_enchants.clear()
        self._slot_entry_indices.clear()

        for si in range(amount):
            self._build_slot_row(si, all_labels)

    def _build_slot_row(self, si: int, all_labels: list[str]):
        """为一个槽位创建：标签 + 条目下拉框 + 详情区。"""
        frame = ttk.LabelFrame(self.locate_slots_frame, text=f"槽位{si + 1}（游戏内第{si + 1}个交易）",
                               padding=5)
        frame.pack(fill="x", pady=2)

        var = tk.StringVar()
        self._slot_combo_vars.append(var)
        combo = ttk.Combobox(frame, textvariable=var, values=all_labels,
                             width=28, state="readonly")
        combo.pack(side="left", padx=5)
        combo.bind("<<ComboboxSelected>>", lambda e, idx=si: self._on_slot_entry_change(idx))
        self._slot_combo_widgets.append(combo)

        detail_frame = ttk.Frame(frame)
        detail_frame.pack(side="left", padx=5)
        self._slot_detail_frames.append(detail_frame)

    # ============================================================
    # 槽位条目选择 → 互斥更新 + 动态详情
    # ============================================================
    def _get_slot_selected_indices(self) -> set[int]:
        """收集所有槽位当前选中的池条目索引。"""
        selected = set()
        for si, var in enumerate(self._slot_combo_vars):
            label = var.get()
            for idx, e in enumerate(self._pool_entries):
                if e["label"] == label:
                    selected.add(idx)
                    break
        return selected

    def _on_slot_entry_change(self, si: int):
        """槽位 si 的条目变化：更新该槽位详情 + 互斥更新其他槽位可选项。"""
        label = self._slot_combo_vars[si].get()
        entry_idx = None
        entry_info = None
        for idx, e in enumerate(self._pool_entries):
            if e["label"] == label:
                entry_idx = idx
                entry_info = e
                break
        if entry_info is None:
            return

        self._slot_entry_indices[si] = entry_idx
        self._slot_enchants.pop(si, None)  # 清空该槽位的附魔选择

        # 更新该槽位的详情区
        detail_frame = self._slot_detail_frames[si]
        for w in detail_frame.winfo_children():
            w.destroy()

        tp = entry_info["type"]
        if tp in ("enchanted_book", "enchanted_equipment"):
            # Store equipment item for enchanted_equipment slots
            if tp == "enchanted_equipment":
                equip_item = entry_info.get("data", {}).get("item", "")
                levels_min = entry_info.get("data", {}).get("levels_min", 5)
                levels_max = entry_info.get("data", {}).get("levels_max", 19)
                setattr(self, f"_slot_equip_item_{si}", equip_item)
                setattr(self, f"_slot_equip_levels_{si}", (levels_min, levels_max))
            self._build_slot_ench_detail(si, detail_frame)
        elif tp == "suspicious_stew":
            self._build_slot_stew_detail(si, detail_frame)
        elif tp == "tipped_arrow":
            self._build_slot_potion_detail(si, detail_frame)
        elif tp == "dyed_equipment":
            self._build_slot_dye_detail(si, detail_frame)
        # other type: 无需详情

        # 互斥更新：其他槽位的可选项中排除已选条目
        self._apply_mutual_exclusion(si)

    def _apply_mutual_exclusion(self, _changed_si: int):
        """更新所有槽位的可选值，排除已被其他槽位选择的条目。
        当池条目数量为1时（如工具匠5级），所有槽位共享唯一条目，无需互斥。"""
        pool_size = len(self._pool_entries)
        if pool_size <= 1:
            return  # 唯一条目，不需要互斥
        all_labels = [e["label"] for e in self._pool_entries]
        selected_indices = self._get_slot_selected_indices()

        for other_si in range(len(self._slot_combo_widgets)):
            if other_si == _changed_si:
                continue
            other_var = self._slot_combo_vars[other_si]
            current = other_var.get()

            # 构建该槽位的可用选项：排除被其他槽位选中的
            available = []
            for idx, label in enumerate(all_labels):
                if idx not in selected_indices or idx == self._slot_entry_indices.get(other_si):
                    available.append(label)

            other_widget = self._slot_combo_widgets[other_si]
            other_widget["values"] = available

            # 如果当前值不在可用列表中，切换到第一个可用
            if current not in available and available:
                other_var.set(available[0])
                self._on_slot_entry_change(other_si)

    # ============================================================
    # 各槽位的详情控件构建（per-slot）
    # ============================================================
    def _build_slot_ench_detail(self, si: int, frame: ttk.Frame):
        """为槽位 si 构建附魔选择 + 价格详情。"""
        btn = ttk.Button(frame, text="点击选择附魔", width=14,
                         command=lambda: self._select_slot_enchant(si))
        btn.pack(side="left", padx=3)
        # 存储按钮引用以便更新文本
        setattr(self, f"_slot_ench_btn_{si}", btn)

        ttk.Label(frame, text="价格:").pack(side="left", padx=(5, 0))
        price_var = tk.StringVar(value="任意")
        price_combo = ttk.Combobox(frame, textvariable=price_var,
                                   values=["任意"], width=8, state="readonly")
        price_combo.pack(side="left", padx=3)
        setattr(self, f"_slot_price_var_{si}", price_var)
        setattr(self, f"_slot_price_combo_{si}", price_combo)

    def _build_slot_stew_detail(self, si: int, frame: ttk.Frame):
        ttk.Label(frame, text="效果:").pack(side="left")
        var = tk.StringVar(value="夜视")
        combo = ttk.Combobox(frame, textvariable=var,
                             values=list(STEW_CN.values()), width=10, state="readonly")
        combo.pack(side="left", padx=3)
        setattr(self, f"_slot_stew_var_{si}", var)

    def _build_slot_potion_detail(self, si: int, frame: ttk.Frame):
        ttk.Label(frame, text="药水:").pack(side="left")
        var = tk.StringVar(value="夜视")
        combo = ttk.Combobox(frame, textvariable=var,
                             values=list(POTION_CN.values()), width=14, state="readonly")
        combo.pack(side="left", padx=3)
        setattr(self, f"_slot_potion_var_{si}", var)

    def _build_slot_dye_detail(self, si: int, frame: ttk.Frame):
        ttk.Label(frame, text="颜色:").pack(side="left")
        var = tk.StringVar(value="白")
        combo = ttk.Combobox(frame, textvariable=var,
                             values=list(DYE_CN.values()), width=6, state="readonly")
        combo.pack(side="left", padx=3)
        setattr(self, f"_slot_dye_var_{si}", var)

    def _select_slot_enchant(self, si: int):
        """打开附魔选择弹窗。附魔书使用 EnchantmentSelector，附魔装备使用 EquipmentEnchantSelector。"""
        entry_idx = self._slot_entry_indices.get(si)
        entry_info = self._pool_entries[entry_idx] if entry_idx is not None else None
        is_equipment = entry_info is not None and entry_info["type"] == "enchanted_equipment"

        if is_equipment:
            equip_item = getattr(self, f"_slot_equip_item_{si}", "")
            levels = getattr(self, f"_slot_equip_levels_{si}", (5, 19))
            selector = EquipmentEnchantSelector(self.root, equip_item, levels[0], levels[1])
            self.root.wait_window(selector)
            if selector.result is not None and len(selector.result) > 0:
                self._slot_enchants[si] = selector.result
                cn_list = [f"{ENCHANTMENT_CN.get(n, n)} {lv}" for n, lv in selector.result]
                btn = getattr(self, f"_slot_ench_btn_{si}", None)
                if btn:
                    btn.config(text=", ".join(cn_list))
        else:
            selector = EnchantmentSelector(self.root)
            self.root.wait_window(selector)
            if selector.result:
                ench, lv = selector.result
                self._slot_enchants[si] = (ench, lv)
                cn = ENCHANTMENT_CN.get(ench, ench)
                btn = getattr(self, f"_slot_ench_btn_{si}", None)
                if btn:
                    btn.config(text=f"{cn} {lv}")
                is_treasure = ench in DOUBLE_PRICE_SET
                base_min = 2 + 3 * lv
                base_max = 6 + 13 * lv
                if is_treasure:
                    base_min *= 2
                    base_max *= 2
                base_min = max(1, min(64, base_min))
                base_max = max(1, min(64, base_max))
                combo = getattr(self, f"_slot_price_combo_{si}", None)
                if combo:
                    combo["values"] = ["任意"] + [str(i) for i in range(base_min, base_max + 1)]
                    combo.current(0)

    # ============================================================
    # 职业/等级变化 → 清空节点定位
    # ============================================================
    def _on_prof_change(self, event=None):
        """职业变化：清空节点定位、刷新池条目。"""
        self._clear_observations()
        self._refresh_pool_entries()
        self.config["last_prof"] = self.prof_var.get()
        save_config(self.config)

    def _on_level_change(self, event=None):
        """等级变化：清空节点定位、刷新池条目。"""
        self._clear_observations()
        self._refresh_pool_entries()
        self.config["last_level"] = self.level_var.get()
        save_config(self.config)

    # ============================================================
    # 观测管理（每个观测 = 全槽位快照）
    # ============================================================
    def _collect_obs_from_slots(self) -> dict | None:
        """从当前所有槽位收集观测数据。每个槽位必须满足类型条件。"""
        slots_data = []
        label_parts = []

        for si in range(len(self._slot_combo_widgets)):
            entry_idx = self._slot_entry_indices.get(si)
            if entry_idx is None:
                messagebox.showwarning("提示", f"槽位{si + 1}未选择条目")
                return None
            entry_info = self._pool_entries[entry_idx]
            tp = entry_info["type"]

            slot = {"entry_info": entry_info}

            if tp == "enchanted_book":
                ench_data = self._slot_enchants.get(si)
                if not ench_data:
                    messagebox.showwarning("提示", f"槽位{si + 1}（附魔书）未选择附魔")
                    return None
                slot["enchantment"], slot["ench_level"] = ench_data
                price_var = getattr(self, f"_slot_price_var_{si}", None)
                price_val = price_var.get() if price_var else "任意"
                slot["price"] = None if price_val == "任意" else int(price_val)
                cn = ENCHANTMENT_CN.get(slot["enchantment"], slot["enchantment"])
                part = f"[{si + 1}]附魔书: {cn} {slot['ench_level']}"
                if slot["price"] is not None:
                    part += f" ({slot['price']}E)"

            elif tp == "enchanted_equipment":
                ench_data = self._slot_enchants.get(si)
                if not ench_data:
                    messagebox.showwarning("提示", f"槽位{si + 1}（附魔装备）未选择附魔")
                    return None
                # ench_data is a list of (name, level) tuples
                slot["enchantments"] = ench_data
                price_var = getattr(self, f"_slot_price_var_{si}", None)
                price_val = price_var.get() if price_var else "任意"
                slot["price"] = None if price_val == "任意" else int(price_val)
                enc_str = ", ".join(f"{ENCHANTMENT_CN.get(n, n)} {lv}" for n, lv in ench_data)
                eq_name = entry_info["label"]
                part = f"[{si + 1}]{eq_name}: [{enc_str}]"
                if slot["price"] is not None:
                    part += f" ({slot['price']}E)"

            elif tp == "suspicious_stew":
                var = getattr(self, f"_slot_stew_var_{si}", None)
                cn = var.get() if var else "?"
                slot["effect"] = STEW_EN.get(cn, cn)
                part = f"[{si + 1}]迷之炖菜: {cn}"

            elif tp == "tipped_arrow":
                var = getattr(self, f"_slot_potion_var_{si}", None)
                cn = var.get() if var else "?"
                slot["potion"] = POTION_EN.get(cn, cn)
                part = f"[{si + 1}]药箭: {cn}"

            elif tp == "dyed_equipment":
                var = getattr(self, f"_slot_dye_var_{si}", None)
                cn = var.get() if var else "?"
                slot["dye"] = cn
                part = f"[{si + 1}]染色装备: {cn}"

            else:
                part = f"[{si + 1}]{entry_info['label']}"

            slots_data.append(slot)
            label_parts.append(part)

        return {"slots": slots_data, "label": "  ".join(label_parts)}

    def _add_observation(self):
        obs = self._collect_obs_from_slots()
        if obs is None:
            return
        self.observations.append(obs)
        self.obs_listbox.insert("end", obs["label"])

    def _remove_observation(self):
        sel = self.obs_listbox.curselection()
        if sel:
            self.obs_listbox.delete(sel[0])
            self.observations.pop(sel[0])

    def _clear_observations(self):
        self.obs_listbox.delete(0, "end")
        self.observations.clear()
        self.locate_result_list.delete(0, "end")
        self.locate_status.config(text="")

    # ============================================================
    # 节点定位面板折叠/展开
    # ============================================================
    def _toggle_locate_panel(self):
        if self._locate_collapsed:
            self.frame_locate.pack(fill="x", padx=10, pady=(0, 5),
                                   after=self._locate_toggle_btn)
            self._locate_toggle_btn.config(text="▽ 节点定位")
            self._locate_collapsed = False
        else:
            self.frame_locate.pack_forget()
            self._locate_toggle_btn.config(text="▷ 节点定位")
            self._locate_collapsed = True

    def _build_obs_match_fn(self):
        """构建单次观测匹配函数；槽位按游戏内位置 i → i 精确匹配。"""
        if not self.observations:
            return None

        def match_fn(trades, obs):
            slots = obs["slots"]
            if len(slots) != len(trades):
                return False

            for si, slot in enumerate(slots):
                if si >= len(trades):
                    return False
                t = trades[si]
                ent_info = slot["entry_info"]
                tp = ent_info["type"]
                t_tp = t.get("type", "other")

                if tp != t_tp:
                    return False

                ent_entry = ent_info["data"].get("entry", "")
                t_entry = t.get("entry", "")
                if tp in ("other", "dyed_equipment") and ent_entry != t_entry:
                    return False

                if tp == "enchanted_book":
                    if (t.get("enchantment") != slot.get("enchantment")
                            or t.get("level") != slot.get("ench_level")):
                        return False
                    if (slot.get("price") is not None
                            and t.get("final_cost") != slot["price"]):
                        return False
                elif tp == "enchanted_equipment":
                    t_enchs = set(tuple(e) for e in t.get("enchantments", []))
                    s_enchs = set(tuple(e) for e in slot.get("enchantments", []))
                    if t_enchs != s_enchs:
                        return False
                    if (slot.get("price") is not None
                            and t.get("final_cost") != slot["price"]):
                        return False
                elif tp == "suspicious_stew":
                    if t.get("effect") != slot.get("effect"):
                        return False
                elif tp == "tipped_arrow":
                    if t.get("potion") != slot.get("potion"):
                        return False
                elif tp == "dyed_equipment":
                    if slot.get("dye") not in t.get("dyes", []):
                        return False

            return True

        return match_fn

    # ============================================================
    # 节点定位
    # ============================================================
    def _do_locate(self):
        if not self.predictor:
            messagebox.showwarning("提示", "请先加载种子")
            return
        if not self.observations:
            messagebox.showwarning("提示", "请先添加观测")
            return

        try:
            search_range = int(self.locate_range_var.get())
        except ValueError:
            messagebox.showerror("错误", "搜索范围必须是整数")
            return

        match_fn = self._build_obs_match_fn()
        if not match_fn:
            return

        prof = self._get_profession_en()
        level = self._get_level()

        self.locate_result_list.delete(0, "end")
        self.locate_status.config(text="搜索中...", foreground="blue")
        self.root.update()

        # 第 j 条观测匹配 offset+j；流式推进一次即可覆盖所有偏移。
        rng = self.predictor.create_rng(prof, level)
        obs_list = list(self.observations)
        candidates = bytearray(b"\x01") * search_range
        generations_to_check = search_range + len(obs_list) - 1

        for generation in range(generations_to_check):
            if generation % 500 == 0:
                progress = min(generation, search_range)
                self.locate_status.config(text=f"搜索中... {progress}/{search_range}", foreground="blue")
                self.root.update()
            try:
                trades = self.predictor.simulate_trades(prof, level, rng)
            except Exception:
                trades = None

            for obs_index, obs in enumerate(obs_list):
                start_offset = generation - obs_index
                if 0 <= start_offset < search_range and candidates[start_offset]:
                    if trades is None or not match_fn(trades, obs):
                        candidates[start_offset] = 0

        matching = [off for off, matched in enumerate(candidates) if matched]

        self.locate_result_list.delete(0, "end")
        if matching:
            for off in matching[:50]:
                try:
                    trades = self.predictor.predict_at_offset(prof, level, off)
                    preview = ", ".join(translate_trade(t) for t in trades)
                    self.locate_result_list.insert("end", f"偏移 {off}: {preview}")
                except Exception:
                    self.locate_result_list.insert("end", f"偏移 {off}")

            status = f"找到 {len(matching)} 个匹配"
            if len(matching) == 1:
                status += " (唯一)"
                self.offset_var.set(str(matching[0]))
                self.locate_status.config(text=status, foreground="green")
            elif len(matching) >= 50:
                self.locate_status.config(text=status + " (仅显示前50)", foreground="orange")
            else:
                self.locate_status.config(text=status + " | 双击偏移可填入", foreground="orange")
        else:
            self.locate_status.config(
                text=f"搜索 0~{search_range-1} 未找到匹配", foreground="red")

    def _locate_continue(self):
        try:
            cur_range = int(self.locate_range_var.get())
        except ValueError:
            return
        new_range = cur_range * 2
        self.locate_range_var.set(str(new_range))
        self._do_locate()

    def _on_locate_result_click(self, event):
        sel = self.locate_result_list.curselection()
        if not sel:
            return
        text = self.locate_result_list.get(sel[0])
        try:
            off = int(text.split()[1].rstrip(":"))
            self.offset_var.set(str(off))
        except (IndexError, ValueError):
            pass

    # ============================================================
    # 核心逻辑
    # ============================================================
    def _get_profession_en(self) -> str:
        return PROFESSION_EN.get(self.prof_var.get(), "librarian")

    def _get_level(self) -> int:
        return int(self.level_var.get()[0])

    def _get_variant(self) -> str | None:
        v = self.variant_var.get()
        if v.startswith("默认"):
            return None
        return v.split("-")[0]

    def _load_seed(self):
        seed_str = self.seed_var.get().strip()
        if not seed_str:
            messagebox.showwarning("提示", "请输入世界种子")
            return
        try:
            seed = int(seed_str, 0)
        except ValueError:
            messagebox.showerror("错误", "种子格式错误，请输入十进制数字")
            return

        self.predictor = VillagerTradePredictor(seed, variant=self._get_variant())
        self.seed_status.config(text=f"已加载种子 {seed}", foreground="green")

        self.config["last_seed"] = seed_str
        history = self.config.get("history", [])
        if seed_str in history:
            history.remove(seed_str)
        history.insert(0, seed_str)
        self.config["history"] = history[:10]
        save_config(self.config)

    def _generate_data(self):
        if not self.predictor:
            messagebox.showwarning("提示", "请先加载种子")
            return False

        variant = self._get_variant()
        if self.predictor.variant != variant:
            self.predictor = VillagerTradePredictor(self.predictor.world_seed, variant=variant)

        try:
            start_offset = int(self.offset_var.get())
            count = int(self.count_var.get())
        except ValueError:
            messagebox.showerror("错误", "起始偏移和导出数量必须是整数")
            return False

        if start_offset < 0:
            messagebox.showerror("错误", "起始偏移不能为负数")
            return False
        if count <= 0 or count > 50000:
            messagebox.showerror("错误", "导出数量需在 1~50000 之间")
            return False

        prof = self._get_profession_en()
        level = self._get_level()

        self.current_data = []
        # 流式推进 RNG：先跳到 start_offset，再顺序生成
        rng = self.predictor.create_rng(prof, level)
        for _ in range(start_offset):
            self.predictor._consume_trade_generation(rng, prof, level)
        for off in range(start_offset, start_offset + count):
            try:
                trades = self.predictor.simulate_trades(prof, level, rng)
            except Exception as e:
                messagebox.showerror("错误", f"预测偏移 {off} 时出错: {e}")
                return False
            for t in trades:
                row = trade_to_csv_row(t, off, level)
                self.current_data.append(row)
            # simulate_trades already advances RNG; no need for extra _consume_trade_generation

        self.filtered_data = list(self.current_data)
        self._populate_filter_options()
        return True

    # ============================================================
    # 筛选：规则式（正反选 + OR连接，选项从数据动态填充）
    # ============================================================
    def _populate_filter_options(self):
        """根据 current_data 动态收集选项，并刷新所有已有规则的下拉框。"""
        if not self.current_data:
            self._filter_type_vals = ["全部"]
            self._filter_ench_vals = ["全部"]
            self._filter_lv_vals = ["任意"]
            self._filter_price_vals = ["全部价格"]
        else:
            # 类型
            types_seen = set()
            for row in self.current_data:
                types_seen.add(row[3])
            type_order = {t: i for i, t in enumerate(TRADE_TYPE_CN)}
            self._filter_type_vals = ["全部"] + sorted(types_seen, key=lambda x: type_order.get(x, 99))

            # 附魔
            enchs_seen = set()
            for row in self.current_data:
                row_type = row[3]
                d1 = str(row[4]) if row[4] else ""
                d2 = str(row[5]) if row[5] else ""
                if row_type == "附魔书":
                    enchs_seen.add(d1)
                elif row_type == "附魔装备":
                    for part in d2.split(";"):
                        part = part.strip()
                        if part:
                            enchs_seen.add(part)
            self._filter_ench_vals = ["全部"] + sorted(enchs_seen)

            # 等级
            lvs_seen = set()
            for row in self.current_data:
                lv = str(row[6])
                if lv and lv != "0":
                    lvs_seen.add(lv)
            self._filter_lv_vals = ["任意"] + sorted(lvs_seen, key=int)

            # 价格：收集实际存在的价格值
            prices_seen = set()
            for row in self.current_data:
                try:
                    p = int(row[7])
                    if 1 <= p <= 64:
                        prices_seen.add(p)
                except (ValueError, TypeError):
                    pass
            price_vals = ["全部价格"] + sorted([str(p) for p in prices_seen], key=int)
            # 添加百分比模式选项
            price_vals += ["-- 百分比 --", "0%", "25%", "50%", "75%", "100%"]
            self._filter_price_vals = price_vals

        # 刷新所有已有规则的下拉框
        self._refresh_rule_dropdowns()

    def _refresh_rule_dropdowns(self):
        """更新所有已有规则的下拉框选项。"""
        for rule in self.filter_rules:
            w = rule["widgets"]
            w["type_combo"]["values"] = self._filter_type_vals
            w["ench_combo"]["values"] = self._filter_ench_vals
            w["lv_combo"]["values"] = self._filter_lv_vals
            w["price_combo"]["values"] = self._filter_price_vals

    def _on_rule_ench_change(self, rule_data: dict):
        """当规则中附魔选择变化时，动态更新等级和价格下拉选项。"""
        if not self.current_data:
            return
        w = rule_data["widgets"]
        ench_sel = w["ench_var"].get()

        if ench_sel == "全部":
            w["lv_combo"]["values"] = self._filter_lv_vals
            w["price_combo"]["values"] = self._filter_price_vals
            return

        # 收集匹配此附魔的等级和价格
        lvs_seen = set()
        prices_seen = set()
        for row in self.current_data:
            row_type = row[3]
            d1 = str(row[4]) if row[4] else ""
            d2 = str(row[5]) if row[5] else ""
            if ench_sel not in d1 and ench_sel not in d2:
                continue
            lv = str(row[6])
            if lv and lv != "0":
                lvs_seen.add(lv)
            try:
                p = int(row[7])
                if 1 <= p <= 64:
                    prices_seen.add(p)
            except (ValueError, TypeError):
                pass

        lv_vals = ["任意"] + sorted(lvs_seen, key=int) if lvs_seen else ["任意"]
        w["lv_combo"]["values"] = lv_vals

        price_vals = ["全部价格"] + sorted([str(p) for p in prices_seen], key=int) if prices_seen else ["全部价格"]
        price_vals += ["-- 百分比 --", "0%", "25%", "50%", "75%", "100%"]
        w["price_combo"]["values"] = price_vals

    def _add_filter_rule(self):
        """添加一条新筛选规则。"""
        if not self.current_data:
            messagebox.showwarning("提示", "请先预览交易数据")
            return

        rule_frame = ttk.LabelFrame(self.filter_rules_frame, text="",
                                    padding=3)
        rule_frame.pack(fill="x", pady=2)

        rule_data = {"mode": "包含", "widgets": {}}
        w = rule_data["widgets"]

        # 模式切换：包含/排除
        mode_var = tk.StringVar(value="包含")
        mode_combo = ttk.Combobox(rule_frame, textvariable=mode_var,
                                  values=["包含", "排除"], width=5, state="readonly")
        mode_combo.pack(side="left", padx=2)
        mode_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_rule_filter())
        w["mode_var"] = mode_var
        w["mode_combo"] = mode_combo

        ttk.Label(rule_frame, text="类型:").pack(side="left", padx=(5, 0))
        type_var = tk.StringVar(value="全部")
        type_combo = ttk.Combobox(rule_frame, textvariable=type_var,
                                  values=self._filter_type_vals, width=10, state="readonly")
        type_combo.pack(side="left", padx=2)
        type_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_rule_filter())
        w["type_var"] = type_var
        w["type_combo"] = type_combo

        ttk.Label(rule_frame, text="附魔:").pack(side="left", padx=(5, 0))
        ench_var = tk.StringVar(value="全部")
        ench_combo = ttk.Combobox(rule_frame, textvariable=ench_var,
                                  values=self._filter_ench_vals, width=14, state="readonly")
        ench_combo.pack(side="left", padx=2)
        ench_combo.bind("<<ComboboxSelected>>", lambda e: self._on_rule_ench_change(rule_data))
        w["ench_var"] = ench_var
        w["ench_combo"] = ench_combo

        ttk.Label(rule_frame, text="等级:").pack(side="left", padx=(5, 0))
        lv_var = tk.StringVar(value="任意")
        lv_combo = ttk.Combobox(rule_frame, textvariable=lv_var,
                                values=self._filter_lv_vals, width=4, state="readonly")
        lv_combo.pack(side="left", padx=2)
        lv_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_rule_filter())
        w["lv_var"] = lv_var
        w["lv_combo"] = lv_combo

        ttk.Label(rule_frame, text="价格:").pack(side="left", padx=(5, 0))
        price_var = tk.StringVar(value="全部价格")
        price_combo = ttk.Combobox(rule_frame, textvariable=price_var,
                                   values=self._filter_price_vals, width=12, state="readonly")
        price_combo.pack(side="left", padx=2)
        price_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_rule_filter())
        w["price_var"] = price_var
        w["price_combo"] = price_combo

        rule_idx = len(self.filter_rules)
        ttk.Button(rule_frame, text="删除",
                   command=lambda idx=rule_idx: self._remove_filter_rule(idx)
                   ).pack(side="left", padx=5)

        # 存储 frame 引用以便删除时查找
        rule_data["frame"] = rule_frame

        # 更新 rule_frame 标题
        rule_frame.config(text=f"规则 {rule_idx + 1}")

        self.filter_rules.append(rule_data)
        self._apply_rule_filter()

    def _remove_filter_rule(self, idx: int):
        """删除指定索引的筛选规则。"""
        if idx < 0 or idx >= len(self.filter_rules):
            return
        rule = self.filter_rules.pop(idx)
        # 销毁对应的 frame
        if "frame" in rule:
            rule["frame"].destroy()
        # 重建所有规则（更新编号和lambda绑定）
        self._rebuild_rule_frames()
        self._apply_rule_filter()

    def _rebuild_rule_frames(self):
        """清空并重建规则框架(重命名规则编号)。"""
        for child in self.filter_rules_frame.winfo_children():
            child.destroy()
        old_rules = list(self.filter_rules)
        self.filter_rules = []
        for rule_data in old_rules:
            self._add_rule_from_data(rule_data)
        # 强制刷新布局，使父容器高度随规则数量自适应
        self.filter_rules_frame.update_idletasks()
        self.filter_rules_frame.master.update_idletasks()

    def _add_rule_from_data(self, rule_data: dict):
        """从 rule_data 重建一条规则的 UI。"""
        rule_frame = ttk.LabelFrame(self.filter_rules_frame, text="", padding=3)
        rule_frame.pack(fill="x", pady=2)
        w = rule_data["widgets"]

        mode_combo = ttk.Combobox(rule_frame, textvariable=w["mode_var"],
                                  values=["包含", "排除"], width=5, state="readonly")
        mode_combo.pack(side="left", padx=2)
        mode_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_rule_filter())
        w["mode_combo"] = mode_combo

        ttk.Label(rule_frame, text="类型:").pack(side="left", padx=(5, 0))
        type_combo = ttk.Combobox(rule_frame, textvariable=w["type_var"],
                                  values=self._filter_type_vals, width=10, state="readonly")
        type_combo.pack(side="left", padx=2)
        type_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_rule_filter())
        w["type_combo"] = type_combo

        ttk.Label(rule_frame, text="附魔:").pack(side="left", padx=(5, 0))
        ench_combo = ttk.Combobox(rule_frame, textvariable=w["ench_var"],
                                  values=self._filter_ench_vals, width=14, state="readonly")
        ench_combo.pack(side="left", padx=2)
        ench_combo.bind("<<ComboboxSelected>>", lambda e: self._on_rule_ench_change(rule_data))
        w["ench_combo"] = ench_combo

        ttk.Label(rule_frame, text="等级:").pack(side="left", padx=(5, 0))
        lv_combo = ttk.Combobox(rule_frame, textvariable=w["lv_var"],
                                values=self._filter_lv_vals, width=4, state="readonly")
        lv_combo.pack(side="left", padx=2)
        lv_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_rule_filter())
        w["lv_combo"] = lv_combo

        ttk.Label(rule_frame, text="价格:").pack(side="left", padx=(5, 0))
        price_combo = ttk.Combobox(rule_frame, textvariable=w["price_var"],
                                   values=self._filter_price_vals, width=12, state="readonly")
        price_combo.pack(side="left", padx=2)
        price_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_rule_filter())
        w["price_combo"] = price_combo

        rule_idx = len(self.filter_rules)
        ttk.Button(rule_frame, text="删除",
                   command=lambda idx=rule_idx: self._remove_filter_rule(idx)
                   ).pack(side="left", padx=5)

        rule_frame.config(text=f"规则 {rule_idx + 1}")
        self.filter_rules.append(rule_data)

    def _get_theoretical_price_range(self, row):
        """返回交易的理论价格范围 (min, max)，基于附魔书公式或装备等级范围。"""
        row_type = row[3]

        if row_type == "附魔书":
            # row[5] = enchantment English name, row[6] = level, row[8] = treasure
            try:
                level = int(row[6])
            except (ValueError, TypeError):
                level = 1
            is_treasure = row[8] == "是"

            # cost = 2 + nextInt(5 + level * 10) + 3 * level
            # Min: nextInt returns 0; Max: nextInt returns (5+level*10 - 1) = 4 + 10*level
            min_cost_raw = 2 + 3 * level
            max_cost_raw = 2 + (4 + 10 * level) + 3 * level  # = 6 + 13*level
            if is_treasure:
                min_cost_raw *= 2
                max_cost_raw *= 2
            min_cost = max(1, min(64, min_cost_raw))
            max_cost = max(1, min(64, max_cost_raw))
            return min_cost, max_cost

        if row_type == "附魔装备":
            # row[4] = item name (without minecraft: prefix), cost = enchant level
            item_name = str(row[4]) if row[4] else ""
            item_full = f"minecraft:{item_name}"
            for params in ENCHANTED_EQUIPMENT_PARAMS.values():
                if params[0] == item_full:
                    return params[1], params[2]
            return 5, 19  # default

        return None, None

    def _apply_rule_filter(self):
        """应用规则式筛选。"""
        if not self.current_data:
            return

        if not self.filter_rules:
            self.filtered_data = list(self.current_data)
            self._refresh_tree()
            self.filter_status.config(text="")
            return

        filtered = []
        for row in self.current_data:
            row_type = row[3]
            d1 = str(row[4]) if row[4] else ""
            d2 = str(row[5]) if row[5] else ""
            row_lv = str(row[6])
            try:
                row_price = int(row[7])
            except (ValueError, TypeError):
                row_price = None

            # 检查所有规则
            matched_include = False
            excluded = False

            for rule in self.filter_rules:
                w = rule["widgets"]
                rule_type = w["type_var"].get()
                rule_lv = w["lv_var"].get()
                rule_price = w["price_var"].get()

                # 类型条件
                if rule_type != "全部" and row_type != rule_type:
                    continue

                # 附魔条件
                rule_ench = w["ench_var"].get()
                if rule_ench != "全部":
                    if row_type not in ("附魔书", "附魔装备"):
                        continue
                    # d1=附魔书中文名/装备物品, d2=装备附魔串（分号分隔）
                    if d1 != rule_ench and rule_ench not in d2:
                        continue

                # 等级条件
                if rule_lv != "任意" and row_type in ("附魔书", "附魔装备"):
                    if row_lv != rule_lv:
                        continue

                # 价格条件
                if rule_price != "全部价格":
                    if row_price is None:
                        continue
                    if rule_price.startswith("--") or rule_price == "":
                        continue
                    if "%" in rule_price:
                        # 百分比模式：基于理论价格范围（非预览数据）
                        pct = int(rule_price.replace("%", ""))
                        theo_min, theo_max = self._get_theoretical_price_range(row)
                        if theo_min is None:
                            continue
                        threshold = theo_min + (theo_max - theo_min) * pct / 100
                        if row_price > threshold:
                            continue
                    elif rule_price.isdigit():
                        # 精确价格匹配
                        if row_price != int(rule_price):
                            continue
                    elif "-" in rule_price:
                        # 价格范围
                        try:
                            parts = rule_price.split("-")
                            p_min = int(parts[0])
                            p_max = int(parts[1])
                        except (ValueError, IndexError):
                            continue
                        if row_price < p_min or row_price > p_max:
                            continue

                # 规则匹配成功
                if rule["mode"] == "包含":
                    matched_include = True
                    break  # OR: 一个包含规则匹配就够了
                else:
                    excluded = True
                    break  # 被排除规则命中，直接排除

            if excluded:
                continue
            if matched_include or not any(r["mode"] == "包含" for r in self.filter_rules):
                filtered.append(row)
            # else: 有包含规则但都不匹配，跳过

        self.filtered_data = filtered
        self._refresh_tree()
        self.filter_status.config(
            text=f"显示 {len(filtered)} / {len(self.current_data)} 条", foreground="blue")

    def _safe_int(self, val):
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def _clear_filter(self):
        self.filter_rules.clear()
        self.filtered_data = list(self.current_data) if self.current_data else []
        self._refresh_tree()
        self.filter_status.config(text="")
        # 彻底销毁并重建 rules frame：避免 tkinter 缓存旧高度
        parent = self.filter_rules_frame.master
        self.filter_rules_frame.destroy()
        self.filter_rules_frame = ttk.Frame(parent)
        self.filter_rules_frame.pack(fill="x", pady=1)

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self.filtered_data:
            self.tree.insert("", "end", values=row)

    def _sort_by(self, col: str):
        col_idx = {"offset": 0, "price": 7}.get(col)
        if col_idx is None:
            return
        reverse = getattr(self, "_sort_reverse", False)
        self._sort_reverse = not reverse
        self.filtered_data.sort(
            key=lambda r: (int(r[col_idx]) if str(r[col_idx]).replace("-", "").isdigit() else 0),
            reverse=reverse
        )
        self._refresh_tree()

    # ============================================================
    # 预览 / 导出
    # ============================================================
    def _preview(self):
        if not self._generate_data():
            return
        self._clear_filter()
        self._refresh_tree()
        prof_cn = self.prof_var.get()
        level_cn = LEVEL_NAMES[self._get_level()]
        self.export_status.config(
            text=f"已预览 {len(self.current_data)} 条交易 ({prof_cn} Lv{self._get_level()}-{level_cn})",
            foreground="blue"
        )

    def _export_csv(self):
        if not self.current_data:
            if not self._generate_data():
                return

        prof = self._get_profession_en()
        level = self._get_level()
        try:
            start_offset = int(self.offset_var.get())
            count = int(self.count_var.get())
        except ValueError:
            return

        export_data = self.current_data
        if self.filtered_data and len(self.filtered_data) != len(self.current_data):
            if messagebox.askyesno("导出筛选数据", f"当前已筛选 {len(self.filtered_data)}/{len(self.current_data)} 条。\n是=导出筛选结果，否=导出全部"):
                export_data = self.filtered_data

        default_name = f"{prof}_L{level}_offset{start_offset}_n{count}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = filedialog.asksaveasfilename(
            title="保存CSV文件",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["偏移", "等级", "交易条目", "类型",
                                 "详情1(附魔/物品)", "详情2(附魔等级/颜色)", "附魔等级",
                                 "价格(E)", "宝藏"])
                writer.writerow([
                    f"种子: {self.predictor.world_seed}",
                    f"职业: {self.prof_var.get()}({prof})",
                    f"等级: {level}-{LEVEL_NAMES[level]}",
                    f"偏移范围: {start_offset} ~ {start_offset + count - 1}",
                    f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"导出条数: {len(export_data)}",
                ])
                writer.writerow([])
                writer.writerow(["偏移", "等级", "交易条目", "类型",
                                 "详情1", "详情2", "附魔等级", "价格(E)", "宝藏"])
                for row in export_data:
                    writer.writerow(row)

            self.export_status.config(
                text=f"已导出 {len(export_data)} 条 -> {os.path.basename(filepath)}",
                foreground="green"
            )
            messagebox.showinfo("导出成功", f"已导出 {len(export_data)} 条交易到:\n{filepath}")

        except Exception as e:
            messagebox.showerror("导出失败", str(e))


def main():
    root = tk.Tk()
    app = TradeExportApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
