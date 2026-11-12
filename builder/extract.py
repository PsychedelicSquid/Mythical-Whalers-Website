"""Reads the game's content out of its Python source into game/data.

The game cannot be imported from a script: importing constants.py opens the
game window and connects to Steam. So this module never imports or runs the
game. It parses the .py files with ast and follows each class the way Python
would: class attributes down the chain of parents, then __init__ from top to
bottom, stepping into the parent's __init__ where the game calls it.

It only understands plain values (numbers, strings, lists, dicts, references
to other classes, picture-loading calls). Anything else it meets in a field
the Wiki publishes is reported as a problem with its file and line. It never
guesses.

The in-game Bestiary (class Bestiary in gui.py) is the specification: its
lists of tabs and hidden classes are read from gui.py on every run.
"""

import ast
import json
import os

from builder import config

# The content modules. quests.py, events.py, dialogue.py and documents/ are
# never opened.
MODULES = ["items", "traits", "abilities", "effects", "mobs", "factions", "crews", "gui", "tools",
           "tooltips", "constants"]

# Calls that load a picture, and the folder each one loads from when it is
# given only a file name.
IMAGE_LOADERS = {
    "load_image": None,
    "get_image": "abilities/images",
    "get_buff": "abilities/buffs",
    "get_effect": "abilities/effects",
}


# ---------------------------------------------------------------------------
# Reading source files
# ---------------------------------------------------------------------------

def load_module(name, problems):
    """Parse one game file into its classes, top-level values and import names."""
    path = os.path.join(config.GAME_SOURCE, name + ".py")
    try:
        # utf-8-sig: abilities.py and battle.py start with a byte-order mark.
        with open(path, encoding="utf-8-sig") as handle:
            source = handle.read()
        tree = ast.parse(source)
    except (OSError, SyntaxError) as error:
        problems.append("%s.py could not be read: %s" % (name, error))
        return None

    module = {"name": name, "classes": {}, "order": [], "values": {}, "aliases": {}}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            info = {"name": node.name, "bases": [], "attrs": {}, "init": None,
                    "methods": {}, "line": node.lineno, "node": node}
            for base in node.bases:
                if isinstance(base, ast.Name):
                    info["bases"].append(base.id)
                elif isinstance(base, ast.Attribute):
                    info["bases"].append(base.attr)
            for item in node.body:
                if isinstance(item, ast.Assign) and len(item.targets) == 1:
                    if isinstance(item.targets[0], ast.Name):
                        info["attrs"][item.targets[0].id] = item.value
                if isinstance(item, ast.FunctionDef):
                    info["methods"][item.name] = item
                    if item.name == "__init__":
                        info["init"] = item
            module["classes"][node.name] = info
            module["order"].append(node.name)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            if isinstance(node.targets[0], ast.Name):
                module["values"][node.targets[0].id] = node.value
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module["aliases"][alias.asname or alias.name] = alias.name
    return module


def parents_first(module, class_name):
    """The class and its parents in this module, oldest ancestor first."""
    found = []
    info = module["classes"].get(class_name)
    if info is None:
        return found
    for base in info["bases"]:
        for name in parents_first(module, base):
            if name not in found:
                found.append(name)
    found.append(class_name)
    return found


def descends_from(module, class_name, ancestor):
    return ancestor in parents_first(module, class_name) and class_name != ancestor


def class_attribute(module, class_name, attribute):
    """The ast node of a class-level value, looking up through the parents."""
    chain = parents_first(module, class_name)
    chain.reverse()
    for name in chain:
        node = module["classes"][name]["attrs"].get(attribute)
        if node is not None:
            return node
    return None


def add_spaces(name):
    """tools.add_spaces: 'FireBreath' -> 'Fire Breath'."""
    result = name[0]
    for character in name[1:]:
        if character.isupper() and result[-1] != " ":
            result += " " + character
        else:
            result += character
    return result


def elixir_spacing(name):
    """The spacing Elixir.__init__ applies to its ability's class name."""
    result = ""
    for character in name:
        if character.isupper():
            result += " " + character
        else:
            result += character
    return result.strip()


# ---------------------------------------------------------------------------
# Working out values
# ---------------------------------------------------------------------------

def unknown(node):
    return {"unknown": ast.unparse(node), "line": getattr(node, "lineno", 0)}


def is_unknown(value):
    """True if the value, or anything inside it, could not be worked out."""
    if isinstance(value, dict):
        if "unknown" in value:
            return True
        for key in value:
            if is_unknown(value[key]):
                return True
    if isinstance(value, list):
        for item in value:
            if is_unknown(item):
                return True
    return False


def evaluate(node, context):
    """Turn an ast expression into a plain value, a {"ref"} or an {"image"}."""
    modules = context["modules"]
    module = context["module"]

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, (ast.List, ast.Tuple)):
        items = []
        for element in node.elts:
            items.append(evaluate(element, context))
        return items

    if isinstance(node, ast.Dict):
        result = {}
        for key_node, value_node in zip(node.keys, node.values):
            if key_node is None:
                return unknown(node)
            key = evaluate(key_node, context)
            if isinstance(key, dict) and "ref" in key:
                key = key["ref"]
            if isinstance(key, (dict, list)):
                return unknown(node)
            result[str(key) if not isinstance(key, str) else key] = evaluate(value_node, context)
        return result

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = evaluate(node.operand, context)
        if isinstance(value, (int, float)):
            return -value
        return unknown(node)

    if isinstance(node, ast.BinOp):
        left = evaluate(node.left, context)
        right = evaluate(node.right, context)
        numbers = isinstance(left, (int, float)) and isinstance(right, (int, float))
        if isinstance(node.op, ast.Add):
            if numbers or (isinstance(left, str) and isinstance(right, str)):
                return left + right
        if isinstance(node.op, ast.Mult) and numbers:
            return left * right
        if isinstance(node.op, ast.Sub) and numbers:
            return left - right
        return unknown(node)

    if isinstance(node, ast.Name):
        if node.id in context["locals"]:
            return context["locals"][node.id]
        if node.id in module["classes"]:
            return {"ref": module["name"] + "." + node.id}
        if node.id in module["values"]:
            return evaluate(module["values"][node.id], context)
        return unknown(node)

    if isinstance(node, ast.Attribute):
        # self.something: an instance value set earlier, else a class value
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            if node.attr in context["attrs"]:
                return context["attrs"][node.attr]
            class_node = class_attribute(module, context["class"], node.attr)
            if class_node is not None:
                return evaluate(class_node, context)
            return unknown(node)
        # Something.__name__: the class's name
        if node.attr == "__name__":
            inner = evaluate(node.value, context)
            if isinstance(inner, dict) and "ref" in inner:
                return inner["ref"].split(".")[-1]
            return unknown(node)
        # items.Harpoon: a class in another content module
        if isinstance(node.value, ast.Name):
            target = module["aliases"].get(node.value.id)
            if target in modules and modules[target] is not None:
                if node.attr in modules[target]["classes"]:
                    return {"ref": target + "." + node.attr}
        return unknown(node)

    if isinstance(node, ast.Subscript):
        container = evaluate(node.value, context)
        index = evaluate(node.slice, context)
        if isinstance(container, list) and isinstance(index, int) and -len(container) <= index < len(container):
            return container[index]
        if isinstance(container, dict) and str(index) in container:
            return container[str(index)]
        return unknown(node)

    if isinstance(node, ast.JoinedStr):
        text = ""
        for part in node.values:
            if isinstance(part, ast.Constant):
                text += str(part.value)
            elif isinstance(part, ast.FormattedValue):
                value = evaluate(part.value, context)
                if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                    return unknown(node)
                text += str(value)
        return text

    if isinstance(node, ast.Call):
        function = node.func
        name = ""
        if isinstance(function, ast.Attribute):
            name = function.attr
        elif isinstance(function, ast.Name):
            name = function.id

        if name in IMAGE_LOADERS:
            arguments = []
            for argument in node.args:
                arguments.append(evaluate(argument, context))
            folder = IMAGE_LOADERS[name]
            if folder is None and len(arguments) == 2:
                if isinstance(arguments[0], str) and isinstance(arguments[1], str):
                    return {"image": arguments[0] + "/" + arguments[1]}
            if folder is not None and len(arguments) == 1 and isinstance(arguments[0], str):
                return {"image": folder + "/" + arguments[0]}
            return unknown(node)

        # animate_strip(picture): the picture, marked as a four-frame strip
        if name == "animate_strip" and len(node.args) == 1:
            inner = evaluate(node.args[0], context)
            if isinstance(inner, dict) and "image" in inner:
                return {"image": inner["image"], "strip": True}
            return unknown(node)

        if name == "list" and len(node.args) == 1:
            inner = evaluate(node.args[0], context)
            if isinstance(inner, list):
                return list(inner)
            return unknown(node)

        # abilities.Melee(self), effects.Haste(), SeaWarden(): building a class
        built = evaluate(function, context)
        if isinstance(built, dict) and "ref" in built:
            return built
        return unknown(node)

    return unknown(node)


def is_parent_init(statement):
    """If the statement calls a parent's __init__, say whose: "super" or a class name."""
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return None
    function = statement.value.func
    if not isinstance(function, ast.Attribute) or function.attr != "__init__":
        return None
    owner = function.value
    if isinstance(owner, ast.Call) and isinstance(owner.func, ast.Name) and owner.func.id == "super":
        return "super"
    if isinstance(owner, ast.Name):
        return owner.id
    return None


def class_with_init(module, class_name):
    """The class whose __init__ runs for class_name: its own, or the nearest parent's."""
    chain = parents_first(module, class_name)
    chain.reverse()
    for name in chain:
        if module["classes"][name]["init"] is not None:
            return name
    return None


def parent_with_init(module, class_name):
    """The class whose __init__ a super().__init__() inside class_name reaches."""
    chain = parents_first(module, class_name)
    chain.reverse()
    for name in chain[1:]:
        if module["classes"][name]["init"] is not None:
            return name
    return None


def run_init(modules, module, owner, instance_class, attrs, depth):
    """Follow owner's __init__ from top to bottom, filling attrs.

    owner is the class whose __init__ is being followed; instance_class is the
    class being built, which decides what self.something means.
    """
    if owner is None or depth > 8:
        return
    function = module["classes"][owner]["init"]
    context = {"modules": modules, "module": module, "class": instance_class,
               "attrs": attrs, "locals": {}}

    for statement in function.body:
        parent = is_parent_init(statement)
        if parent == "super":
            run_init(modules, module, parent_with_init(module, owner), instance_class, attrs, depth + 1)
            continue
        if parent is not None and parent in module["classes"]:
            run_init(modules, module, class_with_init(module, parent), instance_class, attrs, depth + 1)
            continue

        # self.reputation.update({...})
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "update" and len(call.args) == 1:
                target = call.func.value
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    current = attrs.get(target.attr)
                    extra = evaluate(call.args[0], context)
                    if isinstance(current, dict) and isinstance(extra, dict) and not is_unknown(extra):
                        merged = dict(current)
                        merged.update(extra)
                        attrs[target.attr] = merged
            continue

        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]

        # self.ally, self.enemy = 'Ravagers', 'Immortals'
        if isinstance(target, ast.Tuple) and isinstance(statement.value, ast.Tuple):
            if len(target.elts) == len(statement.value.elts):
                for part, value in zip(target.elts, statement.value.elts):
                    if isinstance(part, ast.Attribute) and isinstance(part.value, ast.Name) and part.value.id == "self":
                        attrs[part.attr] = evaluate(value, context)
            continue

        if isinstance(target, ast.Name):
            context["locals"][target.id] = evaluate(statement.value, context)
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
            attrs[target.attr] = evaluate(statement.value, context)


def read_instance(modules, module, class_name):
    """The values an instance of the class would carry after __init__."""
    attrs = {}
    run_init(modules, module, class_with_init(module, class_name), class_name, attrs, 0)
    return attrs


def class_value(modules, module, class_name, attribute, default):
    """A class-level value worked out, or default when the class has none."""
    node = class_attribute(module, class_name, attribute)
    if node is None:
        return default
    context = {"modules": modules, "module": module, "class": class_name, "attrs": {}, "locals": {}}
    return evaluate(node, context)


# ---------------------------------------------------------------------------
# The Bestiary's own rules, read from gui.py
# ---------------------------------------------------------------------------

def bestiary_rules(modules, problems):
    gui = modules["gui"]
    rules = {"hidden_mobs": [], "hidden_items": [], "not_factions": [], "item_tabs": {}}
    info = gui["classes"].get("Bestiary")
    if info is None:
        problems.append("gui.py no longer has a class named Bestiary")
        return rules

    tabs = info["attrs"].get("item_tabs")
    if tabs is None:
        problems.append("gui.Bestiary no longer has item_tabs")
    else:
        rules["item_tabs"] = ast.literal_eval(tabs)

    for method, key in [("build_mobs", "hidden_mobs"), ("build_all_items", "hidden_items")]:
        function = info["methods"].get(method)
        found = False
        if function is not None:
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if isinstance(target, ast.Name) and target.id == "hidden" and isinstance(node.value, ast.Tuple):
                        for element in node.value.elts:
                            if isinstance(element, ast.Attribute):
                                rules[key].append(element.attr)
                        found = True
        if not found:
            problems.append("gui.Bestiary.%s no longer has a 'hidden' tuple" % method)

    function = info["methods"].get("build_factions")
    found = False
    if function is not None:
        for node in ast.walk(function):
            if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.NotIn):
                if isinstance(node.comparators[0], ast.List):
                    rules["not_factions"] = ast.literal_eval(node.comparators[0])
                    found = True
    if not found:
        problems.append("gui.Bestiary.build_factions no longer names the factions it leaves out")
    return rules


def method_literal(info, method, variable, problems):
    """A plain dict or list assigned to a local name inside one of a class's methods."""
    function = info["methods"].get(method)
    if function is not None:
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id == variable:
                    try:
                        return ast.literal_eval(node.value)
                    except ValueError:
                        break
    problems.append("gui.Bestiary.%s no longer has a plain '%s'" % (method, variable))
    return {}


def build_stats(modules, problems):
    """Each stat's name, icon and description, in the order the game lists them.

    They are the Stat classes in tooltips.py; STAT_CLASSES gives the order.
    """
    module = modules["tooltips"]
    result = {"crew": [], "ship": []}
    context = {"modules": modules, "module": module, "class": "Stat", "attrs": {}, "locals": {}}
    if "STAT_CLASSES" not in module["values"]:
        problems.append("tooltips.py no longer defines STAT_CLASSES")
        return result

    crew_names = []
    for reference in refs_in(evaluate(module["values"]["STAT_CLASSES"], context)):
        crew_names.append(reference.split(".")[1])
    ship_names = []
    for name in module["order"]:
        if descends_from(module, name, "ShipStat"):
            ship_names.append(name)

    for group, names in [("crew", crew_names), ("ship", ship_names)]:
        for name in names:
            stat = {}
            for key in ["icon_name", "name", "description"]:
                value = class_value(modules, module, name, key, "")
                if not isinstance(value, str) or value == "":
                    problems.append("%s: could not read '%s'" % (where(module, name), key))
                    value = ""
                stat[key] = value
            result[group].append({"icon": stat["icon_name"], "name": stat["name"],
                                  "description": stat["description"]})
    return result


def whale_classes(modules):
    """Mobs fielded by a crew whose faction is 'Leviathan' are the whales."""
    crews = modules["crews"]
    whales = []
    for name in crews["order"]:
        attrs = read_instance(modules, crews, name)
        if attrs.get("faction") != "Leviathan":
            continue
        for key in ["crewmates", "mobs"]:
            fielded = attrs.get(key)
            if isinstance(fielded, list):
                for entry in fielded:
                    if isinstance(entry, dict) and "ref" in entry and entry["ref"].startswith("mobs."):
                        whales.append(entry["ref"].split(".")[1])
    return whales


# ---------------------------------------------------------------------------
# Building the records
# ---------------------------------------------------------------------------

def where(module, class_name):
    return "%s.py line %d (class %s)" % (module["name"], module["classes"][class_name]["line"], class_name)


def need(value, field, module, class_name, problems):
    """Report a published field that could not be worked out. Returns True if it is usable."""
    if is_unknown(value):
        problems.append("%s: could not read '%s'" % (where(module, class_name), field))
        return False
    return True


def image_of(value):
    if isinstance(value, dict) and "image" in value:
        return value["image"]
    return ""


def ref_of(value):
    if isinstance(value, dict) and "ref" in value:
        return value["ref"]
    return ""


def refs_in(value):
    """Every class reference in a list, in order."""
    found = []
    if isinstance(value, list):
        for item in value:
            reference = ref_of(item)
            if reference:
                found.append(reference)
    return found


def build_items(modules, rules, report, problems):
    module = modules["items"]
    records = {}
    tab_of = {}
    for tab in rules["item_tabs"]:
        for item_type in rules["item_tabs"][tab]:
            tab_of[item_type] = tab

    for name in module["order"]:
        if not descends_from(module, name, "Item") or name in rules["hidden_items"]:
            continue
        attrs = read_instance(modules, module, name)

        item_type = attrs.get("type")
        if not isinstance(item_type, str) or item_type not in tab_of:
            problems.append("%s: its type %r is in no Bestiary tab" % (where(module, name), item_type))
            continue

        display = attrs.get("name")
        if not isinstance(display, str):
            display = add_spaces(name)

        description = attrs.get("description", "")
        if descends_from(module, name, "Elixir"):
            # Elixir.__init__ replaces whatever the subclass wrote.
            ability = ref_of(attrs.get("ability")) or ref_of(class_value(modules, module, name, "ability", None))
            if ability:
                description = "Grants %s ability" % elixir_spacing(ability.split(".")[-1])
        if is_unknown(description) or not isinstance(description, str):
            problems.append("%s: could not read 'description'" % where(module, name))
            description = ""
        if description.strip().lower() == display.strip().lower():
            report["placeholder_descriptions"].append(display)
            description = ""

        modifiers = attrs.get("modifiers", {})
        if not need(modifiers, "modifiers", module, name, problems) or not isinstance(modifiers, dict):
            modifiers = {}
        cost = attrs.get("cost", 0)
        if not isinstance(cost, (int, float)):
            cost = 0
        resource = attrs.get("resource")
        if not isinstance(resource, str):
            resource = class_value(modules, module, name, "resource", "gold")

        ability = ref_of(attrs.get("ability")) or ref_of(class_value(modules, module, name, "ability", None))
        grants = ref_of(attrs.get("grants_trait")) or ref_of(class_value(modules, module, name, "grants_trait", None))
        cures = ref_of(class_value(modules, module, name, "cures", None))
        image = image_of(attrs.get("image"))
        if not image:
            problems.append("%s: could not read its icon" % where(module, name))

        slot = attrs.get("slot", "")
        arms = attrs.get("idle_arms", "")
        records["items." + name] = {
            "name": display,
            "tab": tab_of[item_type],
            "type": item_type,
            "slot": slot if isinstance(slot, str) else "",
            "arms": arms if isinstance(arms, str) else "",
            "description": description,
            "modifiers": modifiers,
            "cost": cost,
            "resource": resource,
            "ability": ability,
            "grants_trait": grants,
            "cures": cures,
            "image": image,
        }
    return records


def build_traits(modules, problems):
    module = modules["traits"]
    offerable = []
    if "OFFERABLE_TRAITS" in module["values"]:
        context = {"modules": modules, "module": module, "class": "Trait", "attrs": {}, "locals": {}}
        for reference in refs_in(evaluate(module["values"]["OFFERABLE_TRAITS"], context)):
            offerable.append(reference)

    records = {}
    for name in module["order"]:
        if not descends_from(module, name, "Trait"):
            continue
        # A secret trait is left out, and never named in this public repository.
        if class_value(modules, module, name, "secret", False) is True:
            continue
        attrs = read_instance(modules, module, name)

        display = attrs.get("name")
        if not isinstance(display, str):
            display = add_spaces(name)
        description = attrs.get("description", "")
        if not need(description, "description", module, name, problems) or not isinstance(description, str):
            description = ""
        scaling = attrs.get("scaling")
        if scaling is None:
            scaling = class_value(modules, module, name, "scaling", {})
        if not need(scaling, "scaling", module, name, problems) or not isinstance(scaling, dict):
            scaling = {}
        max_level = class_value(modules, module, name, "max_level", 3)
        image = image_of(attrs.get("image"))
        if not image:
            problems.append("%s: could not read its icon" % where(module, name))

        records["traits." + name] = {
            "name": display,
            "description": description,
            "modifiers": scaling,
            "max_level": max_level,
            "offered_at_level_up": ("traits." + name) in offerable,
            "image": image,
        }
    return records


STAT_KEYS = ["max_hp", "armor", "max_mana", "will", "strength", "luck", "max_stamina", "speed"]


def build_mobs(modules, rules, whales, trait_records, problems):
    module = modules["mobs"]
    records = {}
    for name in module["order"]:
        if not descends_from(module, name, "Mob") or name in rules["hidden_mobs"]:
            continue
        attrs = read_instance(modules, module, name)

        if descends_from(module, name, "Crewmate"):
            group = "crewmate"
        elif name in whales:
            group = "whale"
        elif descends_from(module, name, "Boss"):
            group = "boss"
        elif descends_from(module, name, "Captain"):
            group = "captain"
        else:
            group = "creature"

        stats = attrs.get("stats", {})
        shown = {}
        if need(stats, "stats", module, name, problems) and isinstance(stats, dict):
            for key in STAT_KEYS:
                if key not in stats:
                    problems.append("%s: stats has no '%s'" % (where(module, name), key))
                else:
                    shown[key] = stats[key]

        description = class_value(modules, module, name, "description", "")
        if is_unknown(description) or not isinstance(description, str):
            description = ""

        immunities = attrs.get("immunities")
        if immunities is None:
            immunities = class_value(modules, module, name, "immunities", [])
        if is_unknown(immunities) or not isinstance(immunities, list):
            immunities = []

        abilities = []
        for key in ["move", "default_ability"]:
            reference = ref_of(attrs.get(key))
            if reference:
                abilities.append(reference)
        for reference in refs_in(attrs.get("special_abilities")):
            abilities.append(reference)

        record = {
            "name": add_spaces(name),
            "group": group,
            "description": description,
            "stats": shown,
            "immunities": immunities,
            "abilities": abilities,
            "drops": refs_in(attrs.get("loot")),
            "drop_chance": class_value(modules, module, name, "drop_chance", 0.5),
            "image": "",
        }

        cls = attrs.get("cls")
        if group == "crewmate":
            pool = class_value(modules, module, name, "portrait_pool", {})
            portraits = []
            if isinstance(pool, dict) and not is_unknown(pool):
                for key in pool:
                    for file_name in pool[key]:
                        portraits.append("portraits/" + file_name)
            names = class_value(modules, module, name, "name_pool", {})
            name_list = []
            if isinstance(names, dict) and not is_unknown(names):
                for key in names:
                    for person in names[key]:
                        name_list.append(person)

            # A race can be born with a secret trait. The game lists it nowhere
            # until an event reveals it, and it has no record, so it is left
            # out here as well.
            innate = []
            for pair in class_value(modules, module, name, "innate_traits", []):
                if isinstance(pair, list) and len(pair) == 2 and ref_of(pair[0]) in trait_records:
                    innate.append({"trait": ref_of(pair[0]), "level": pair[1]})

            tiers = {}
            raw_tiers = class_value(modules, module, name, "trait_tiers", {})
            if isinstance(raw_tiers, dict) and not is_unknown(raw_tiers):
                for tier in raw_tiers:
                    tiers[tier] = refs_in(raw_tiers[tier])

            gear = {}
            raw_gear = class_value(modules, module, name, "equipment_sets", {})
            if isinstance(raw_gear, dict) and not is_unknown(raw_gear):
                for level in raw_gear:
                    sets = []
                    for one_set in raw_gear[level]:
                        sets.append(refs_in(one_set))
                    gear[str(level)] = sets

            record["portraits"] = portraits
            record["names"] = name_list
            record["hire_cost"] = class_value(modules, module, name, "hire_cost", 0)
            record["innate_traits"] = innate
            record["trait_tiers"] = tiers
            record["starting_gear"] = gear
            if portraits:
                record["image"] = portraits[0]
        elif isinstance(cls, str):
            record["image"] = "mobs/mobs/%s_idle.png" % cls
        else:
            problems.append("%s: could not read 'cls', which names its sprite" % where(module, name))

        records["mobs." + name] = record
    return records


def build_factions(modules, rules, mob_records, problems):
    module = modules["factions"]
    records = {}
    for name in module["order"]:
        if not descends_from(module, name, "Faction"):
            continue
        attrs = read_instance(modules, module, name)
        display = attrs.get("name")
        if not isinstance(display, str):
            display = add_spaces(name)
        if display in rules["not_factions"]:
            continue

        description = attrs.get("description", "")
        if not need(description, "description", module, name, problems) or not isinstance(description, str):
            description = ""

        members = []
        for reference in refs_in(attrs.get("members")):
            if reference in mob_records:
                members.append(reference)

        heralds = []
        raw_heralds = attrs.get("heralds", {})
        if isinstance(raw_heralds, dict):
            for key in raw_heralds:
                heralds.append(add_spaces(key))

        sites = attrs.get("sites", [])
        site_names = []
        if isinstance(sites, list):
            for site in sites:
                if isinstance(site, str):
                    site_names.append(add_spaces(site))

        ally = attrs.get("ally", "")
        enemy = attrs.get("enemy", "")
        records["factions." + name] = {
            "name": display,
            "description": description,
            "members": members,
            "heralds": heralds,
            "sites": site_names,
            "ally": ally if isinstance(ally, str) else "",
            "enemy": enemy if isinstance(enemy, str) else "",
            "image": image_of(attrs.get("banner")),
        }
    return records


def status_effects_of(modules, ability_name, attrs):
    """The status effects an ability can put on a mob.

    An ability names them in its own code: effects.Feared() in a method, or a
    tile effect such as effects.Fire, which in turn names the buff it leaves
    (Burning). Parents are not searched, because the base classes mention
    effects that have nothing to do with the ability at hand.
    """
    abilities = modules["abilities"]
    effects = modules["effects"]

    named = []
    for key in ["buff", "effect"]:
        reference = ref_of(attrs.get(key))
        if reference.startswith("effects."):
            named.append(reference.split(".")[1])
    for node in ast.walk(abilities["classes"][ability_name]["node"]):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if abilities["aliases"].get(node.value.id) == "effects" and node.attr in effects["classes"]:
                named.append(node.attr)

    found = []
    for name in named:
        if descends_from(effects, name, "Buff"):
            if name not in found:
                found.append(name)
            continue
        # A tile effect: the buffs its own code names.
        for node in ast.walk(effects["classes"][name]["node"]):
            if isinstance(node, ast.Name) and node.id in effects["classes"]:
                if descends_from(effects, node.id, "Buff") and node.id not in found:
                    found.append(node.id)

    references = []
    for name in found:
        references.append("effects." + name)
    return references


def build_abilities(modules, wanted, problems):
    """Only abilities that a published item or mob refers to are published."""
    module = modules["abilities"]
    records = {}
    for reference in wanted:
        name = reference.split(".")[1]
        if name not in module["classes"]:
            problems.append("abilities.py has no class named %s, which something refers to" % name)
            continue
        attrs = read_instance(modules, module, name)
        description = class_value(modules, module, name, "description", "")
        if is_unknown(description) or not isinstance(description, str):
            description = ""
        base = attrs.get("base_stats", {})
        if is_unknown(base) or not isinstance(base, dict):
            base = {}

        record = {
            "name": add_spaces(name),
            "description": description,
            "type": "",
            "damage_type": "",
            "base_stats": base,
            "stamina_cost": 0,
            "mana_cost": 0,
            "status_effects": status_effects_of(modules, name, attrs),
            "image": image_of(attrs.get("image")),
        }
        for key in ["type", "damage_type"]:
            if isinstance(attrs.get(key), str):
                record[key] = attrs[key]
        for key in ["stamina_cost", "mana_cost"]:
            if isinstance(attrs.get(key), (int, float)) and not isinstance(attrs.get(key), bool):
                record[key] = attrs[key]
        records[reference] = record
    return records


def build_effects(modules, wanted, problems):
    module = modules["effects"]
    records = {}
    for reference in wanted:
        name = reference.split(".")[1]
        if name not in module["classes"]:
            problems.append("effects.py has no class named %s, which something refers to" % name)
            continue
        if not descends_from(module, name, "Buff"):
            continue
        attrs = read_instance(modules, module, name)
        description = class_value(modules, module, name, "description", "")
        if is_unknown(description) or not isinstance(description, str):
            description = ""
        duration = attrs.get("duration", 0)
        key = attrs.get("name")
        records[reference] = {
            "name": add_spaces(name),
            # The word a mob's immunities list uses for this effect.
            "key": key if isinstance(key, str) else "",
            "description": description,
            "duration": duration if isinstance(duration, int) and not isinstance(duration, bool) else 0,
            "image": image_of(attrs.get("icon")),
        }
    return records


def sorted_unique(values):
    seen = {}
    for value in values:
        seen[value] = True
    result = list(seen.keys())
    result.sort()
    return result


def references_in(value, found):
    """Collect every reference inside a record: the strings evaluate writes as 'module.Class'."""
    if isinstance(value, str):
        parts = value.split(".")
        if len(parts) == 2 and parts[0] in MODULES and parts[1].isidentifier():
            found.append(value)
    elif isinstance(value, list):
        for item in value:
            references_in(item, found)
    elif isinstance(value, dict):
        for key in value:
            references_in(key, found)
            references_in(value[key], found)


def check_references(modules, record_groups, problems):
    """Report every record that names a class with no record of its own.

    A Wiki page shows whatever its record names, so a reference to a class the
    extract left out (a secret trait, an item the Bestiary hides) would publish
    that class's name.
    """
    published = {}
    for records in record_groups:
        for key in records:
            published[key] = records[key]
    for key in published:
        found = []
        references_in(published[key], found)
        for reference in sorted_unique(found):
            if reference not in published:
                source, name = key.split(".")
                problems.append("%s: refers to %s, which is not published" % (where(modules[source], name), reference))


def read_game(problems):
    """Return {file name: records} for game/data, and a report of what was found."""
    modules = {}
    for name in MODULES:
        modules[name] = load_module(name, problems)
    if problems:
        return {}, {}

    report = {"placeholder_descriptions": []}
    rules = bestiary_rules(modules, problems)
    whales = whale_classes(modules)

    items = build_items(modules, rules, report, problems)
    traits = build_traits(modules, problems)
    mobs = build_mobs(modules, rules, whales, traits, problems)
    factions = build_factions(modules, rules, mobs, problems)

    wanted_abilities = []
    for key in items:
        if items[key]["ability"]:
            wanted_abilities.append(items[key]["ability"])
    for key in mobs:
        for reference in mobs[key]["abilities"]:
            wanted_abilities.append(reference)
    abilities = build_abilities(modules, sorted_unique(wanted_abilities), problems)

    wanted_effects = []
    for key in abilities:
        for reference in abilities[key]["status_effects"]:
            wanted_effects.append(reference)
    effects = build_effects(modules, sorted_unique(wanted_effects), problems)
    check_references(modules, [items, traits, mobs, factions, abilities, effects], problems)

    constants = modules["constants"]
    meta = {"version": "", "storm_interval": 0}
    if "VERSION" in constants["values"]:
        meta["version"] = ast.literal_eval(constants["values"]["VERSION"])
    if "STORM_INTERVAL" in constants["values"]:
        meta["storm_interval"] = ast.literal_eval(constants["values"]["STORM_INTERVAL"])

    # The icon tables the Bestiary uses when it draws an entry.
    bestiary = modules["gui"]["classes"].get("Bestiary")
    if bestiary is not None:
        meta["item_icons"] = method_literal(bestiary, "populate_item", "icon_map", problems)
        meta["trait_icons"] = method_literal(bestiary, "populate_trait", "icon_map", problems)
        meta["immunity_icons"] = method_literal(bestiary, "populate_mob", "buff_icons", problems)

    data = {
        "stats.json": build_stats(modules, problems),
        "items.json": items,
        "traits.json": traits,
        "mobs.json": mobs,
        "factions.json": factions,
        "abilities.json": abilities,
        "effects.json": effects,
        "meta.json": meta,
    }
    report["mobs_without_description"] = []
    for key in mobs:
        if mobs[key]["description"] == "":
            report["mobs_without_description"].append(mobs[key]["name"])
    report["mobs_without_description"].sort()
    report["placeholder_descriptions"].sort()
    return data, report


def as_text(records):
    return json.dumps(records, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def extract(problems):
    """Write game/data. Returns a list of lines describing what changed."""
    data, report = read_game(problems)
    if problems:
        return []

    lines = []
    if not os.path.isdir(config.GAME_DATA):
        os.makedirs(config.GAME_DATA)
    file_names = list(data.keys())
    file_names.sort()
    for file_name in file_names:
        path = os.path.join(config.GAME_DATA, file_name)
        text = as_text(data[file_name])
        before = {}
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                old_text = handle.read()
            if old_text == text:
                continue
            before = json.loads(old_text)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        if file_name in ["meta.json", "stats.json"]:
            lines.append(file_name + " changed")
            continue
        added = []
        removed = []
        for key in data[file_name]:
            if key not in before:
                added.append(key)
        for key in before:
            if key not in data[file_name]:
                removed.append(key)
        added.sort()
        removed.sort()
        lines.append("%s: %d entries, %d new, %d gone" % (file_name, len(data[file_name]), len(added), len(removed)))
        for key in added[:12]:
            lines.append("    new  " + key)
        for key in removed[:12]:
            lines.append("    gone " + key)

    counts = {}
    for key in data["mobs.json"]:
        group = data["mobs.json"][key]["group"]
        counts[group] = counts.get(group, 0) + 1
    tabs = {}
    for key in data["items.json"]:
        tab = data["items.json"][key]["tab"]
        tabs[tab] = tabs.get(tab, 0) + 1
    lines.append("mobs %d %s" % (len(data["mobs.json"]), json.dumps(counts, sort_keys=True)))
    lines.append("items %d %s" % (len(data["items.json"]), json.dumps(tabs, sort_keys=True)))
    lines.append("traits %d, abilities %d, status effects %d, factions %d"
                 % (len(data["traits.json"]), len(data["abilities.json"]),
                    len(data["effects.json"]), len(data["factions.json"])))
    lines.append("%d mobs have no description; %d items have a description that only repeats their name"
                 % (len(report["mobs_without_description"]), len(report["placeholder_descriptions"])))
    return lines
