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
MODULES = ["items", "traits", "abilities", "effects", "mobs", "factions", "locations", "crews", "gui",
           "inventory", "tools", "tooltips", "constants"]

# Calls that load a picture, and the folder each one loads from when it is
# given only a file name.
IMAGE_LOADERS = {
    "load_image": None,
    "get_image": "abilities/images",
    "get_buff": "abilities/buffs",
    "get_effect": "abilities/effects",
    "get_location_image": "locations",
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
        if "ref" in value:
            # Something built from a class. What was changed on it afterwards
            # is checked by whoever publishes those changes.
            return False
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
        # self.something: a value the instance already carries
        if isinstance(node.value, ast.Name) and node.value.id == "self":
            if node.attr in context["attrs"]:
                return context["attrs"][node.attr]
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
                # items.whale_port_items: a value another content module defines
                if node.attr in modules[target]["values"]:
                    elsewhere = {"modules": modules, "module": modules[target], "attrs": {}, "locals": {}}
                    return evaluate(modules[target]["values"][node.attr], elsewhere)
        return unknown(node)

    if isinstance(node, ast.Subscript):
        # c.FACTIONS['Empire']: the faction the game builds under that name
        # (factions.initialize_factions), which is the class of the same name.
        held = node.value
        if isinstance(held, ast.Attribute) and held.attr == "FACTIONS" and isinstance(held.value, ast.Name):
            if module["aliases"].get(held.value.id) == "constants" and isinstance(node.slice, ast.Constant):
                if node.slice.value in modules["factions"]["classes"]:
                    return {"ref": "factions.%s" % node.slice.value}
                return unknown(node)
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

        # picture.convert(), picture.convert_alpha(): the same picture
        if name in ["convert", "convert_alpha"] and isinstance(function, ast.Attribute) and not node.args:
            return evaluate(function.value, context)

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


def self_attribute(node):
    """The name x when node is self.x, else None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        return node.attr
    return None


def root_attribute(node):
    """The name x when node is self.x or is reached through it (self.x.y, self.x[k]), else None."""
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        if self_attribute(node) is not None:
            return node.attr
        node = node.value
    return None


def assign(target, value, context):
    """Give one assignment target its value. False if the target is not one the reader follows."""
    if isinstance(target, ast.Name):
        context["locals"][target.id] = value
        return True
    if self_attribute(target) is not None:
        context["attrs"][target.attr] = value
        return True
    return change(target, value, False, context)


def change(target, value, adds, context):
    """Keep a change to something the instance has built.

    bullet.mana_cost = 1, fire_breath.base_stats['radius'] = 4 and
    ability.base_stats['damage'] += 2 change an ability after it was built.
    The changes are kept on that thing, in order, under "changes", so whatever
    holds it carries them too (see apply_changes). False if the target is not
    such a thing.
    """
    key = None
    if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
        key = str(target.slice.value)
        target = target.value
    if not isinstance(target, ast.Attribute):
        return False
    built = evaluate(target.value, context)
    if not isinstance(built, dict) or "ref" not in built:
        return False
    if "changes" not in built:
        built["changes"] = []
    built["changes"].append({"attr": target.attr, "key": key, "adds": adds, "value": value})
    return True


def apply_changes(attrs, changes):
    """The values of something an instance built, after the changes made to it since."""
    lost = {"unknown": "a change the reader could not apply", "line": 0}
    result = dict(attrs)
    for one in changes:
        current = result.get(one["attr"])
        if one["key"] is not None:
            if not isinstance(current, dict) or is_unknown(current):
                result[one["attr"]] = lost
                continue
            current = current.get(one["key"])
        value = one["value"]
        if one["adds"]:
            numbers = isinstance(current, (int, float)) and isinstance(value, (int, float))
            if numbers and not isinstance(current, bool) and not isinstance(value, bool):
                value = current + value
            else:
                value = lost
        if one["key"] is None:
            result[one["attr"]] = value
        else:
            changed = dict(result[one["attr"]])
            changed[one["key"]] = value
            result[one["attr"]] = changed
    return result


def follow(statement, context):
    """Apply one statement of a method to the instance. False if it is not one the reader follows."""
    attrs = context["attrs"]

    # ability.base_stats['damage'] += 2
    if isinstance(statement, ast.AugAssign) and isinstance(statement.op, ast.Add):
        if not isinstance(statement.target, ast.Name) and self_attribute(statement.target) is None:
            return change(statement.target, evaluate(statement.value, context), True, context)
        return False

    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target = statement.targets[0]
        # self.ally, self.enemy = 'Ravagers', 'Immortals'
        if isinstance(target, ast.Tuple):
            if not isinstance(statement.value, ast.Tuple) or len(target.elts) != len(statement.value.elts):
                return False
            for part, value in zip(target.elts, statement.value.elts):
                if not assign(part, evaluate(value, context), context):
                    return False
            return True
        return assign(target, evaluate(statement.value, context), context)

    # self.reputation.update({...}), self.immunities.append('push')
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
        call = statement.value
        if isinstance(call.func, ast.Attribute) and len(call.args) == 1 and not call.keywords:
            name = self_attribute(call.func.value)
            if name is not None:
                current = attrs.get(name)
                given = evaluate(call.args[0], context)
                if call.func.attr == "update" and isinstance(current, dict) and isinstance(given, dict):
                    merged = dict(current)
                    merged.update(given)
                    attrs[name] = merged
                    return True
                if call.func.attr == "append" and isinstance(current, list):
                    attrs[name] = current + [given]
                    return True
                if call.func.attr == "extend" and isinstance(current, list) and isinstance(given, list):
                    attrs[name] = current + given
                    return True
    return False


# The methods by which Python changes a list, dict or set in place.
CHANGING_METHODS = ["append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse",
                    "update", "setdefault", "popitem", "add", "discard"]


def changed_by(statement):
    """What a statement changes: the instance values (each self.x it assigns
    to or changes in place) and the local names it assigns to."""
    values = []
    names = []
    for node in ast.walk(statement):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.For)):
            targets = [node.target]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in CHANGING_METHODS:
                targets = [node.func.value]
        for target in targets:
            parts = [target]
            if isinstance(target, ast.Tuple):
                parts = target.elts
            for part in parts:
                if isinstance(part, ast.Name):
                    if part.id not in names:
                        names.append(part.id)
                else:
                    value = root_attribute(part)
                    if value is not None and value not in values:
                        values.append(value)
    return values, names


def forget(statement, context):
    """Leave unknown everything a statement the reader did not follow may have changed."""
    values, names = changed_by(statement)
    for value in values:
        context["attrs"][value] = unknown(statement)
    for name in names:
        context["locals"][name] = unknown(statement)


def parameters(modules, module, function, call, caller):
    """What a method's parameters hold when it starts.

    The value the call passes, else the parameter's default: the Bestiary
    builds every entry with no arguments (Feared() lasts its default 1 turn).
    A parameter with neither is unknown. call is None for the instance being
    built; otherwise it is the parent's __init__ call, read in the caller's context.
    """
    names = []
    for argument in function.args.args[1:]:
        names.append(argument.arg)

    values = {}
    scope = {"modules": modules, "module": module, "attrs": {}, "locals": {}}
    defaults = function.args.defaults
    first = len(names) - len(defaults)
    for position in range(len(defaults)):
        values[names[first + position]] = evaluate(defaults[position], scope)

    if call is not None:
        passed = call.args
        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
            # Parent.__init__(self, ...): the first argument is the instance itself
            passed = passed[1:]
        for position in range(min(len(passed), len(names))):
            values[names[position]] = evaluate(passed[position], caller)
        for keyword in call.keywords:
            if keyword.arg in names:
                values[keyword.arg] = evaluate(keyword.value, caller)
    return values


def run_init(modules, module, owner, instance_class, attrs, call, caller, depth):
    """Follow owner's __init__ from top to bottom, changing attrs as it would.

    owner is the class whose __init__ is being followed; instance_class is the
    class being built, which decides what self.something means. call and
    caller say how a child's __init__ called this one (see parameters).

    A statement the reader does not follow (a loop, a condition) leaves every
    value it changes unknown, so that a record which needs one of them reports
    it instead of publishing a guess. A call to another method of the instance
    (self.generate()) is not followed, and what it changes is not tracked.
    """
    if owner is None or depth > 8:
        return
    function = module["classes"][owner]["init"]
    context = {"modules": modules, "module": module, "attrs": attrs,
               "locals": parameters(modules, module, function, call, caller)}

    for statement in function.body:
        parent = is_parent_init(statement)
        if parent == "super":
            run_init(modules, module, parent_with_init(module, owner), instance_class, attrs,
                     statement.value, context, depth + 1)
        elif parent is not None and parent in module["classes"]:
            run_init(modules, module, class_with_init(module, parent), instance_class, attrs,
                     statement.value, context, depth + 1)
        elif not follow(statement, context):
            forget(statement, context)


def class_values(modules, module, class_name):
    """Every class-level value an instance starts with. A class's own value replaces its parent's."""
    values = {}
    for name in parents_first(module, class_name):
        # A class body sees the names it has already assigned, such as the one
        # list of names the Mer give both of their body types.
        body = {}
        context = {"modules": modules, "module": module, "attrs": {}, "locals": body}
        nodes = module["classes"][name]["attrs"]
        for attribute in nodes:
            body[attribute] = evaluate(nodes[attribute], context)
        for attribute in body:
            values[attribute] = body[attribute]
    return values


def read_instance(modules, module, class_name):
    """The values an instance of the class carries, as Python would look them
    up: its class-level values, and over them whatever __init__ sets."""
    attrs = class_values(modules, module, class_name)
    run_init(modules, module, class_with_init(module, class_name), class_name, attrs, None, None, 0)
    return attrs


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

    They are the Stat classes in tooltips.py. STAT_CLASSES gives the order of
    a crewmate's, and the ship's inventory screen (inventory.ShipInventory)
    the order of the ship's.
    """
    module = modules["tooltips"]
    result = {"crew": [], "ship": []}
    context = {"modules": modules, "module": module, "attrs": {}, "locals": {}}
    if "STAT_CLASSES" not in module["values"]:
        problems.append("tooltips.py no longer defines STAT_CLASSES")
        return result

    crew_names = []
    for reference in refs_in(evaluate(module["values"]["STAT_CLASSES"], context)):
        crew_names.append(reference.split(".")[1])
    ship_names = []
    inventory = modules["inventory"]
    if "ShipInventory" not in inventory["classes"]:
        problems.append("inventory.py no longer has a class named ShipInventory")
    else:
        screen = read_instance(modules, inventory, "ShipInventory")
        shown = published(screen, "stat_objects", [], inventory, "ShipInventory", problems)
        for found in named(shown, "stat_objects", inventory, "ShipInventory", problems):
            ship_names.append(found.split(".")[1])

    for group, names in [("crew", crew_names), ("ship", ship_names)]:
        for name in names:
            attrs = read_instance(modules, module, name)
            stat = {}
            for key in ["icon_name", "name", "description"]:
                stat[key] = published(attrs, key, "", module, name, problems)
                if stat[key] == "":
                    problems.append("%s: has no '%s'" % (where(module, name), key))
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


def published(attrs, key, default, module, class_name, problems):
    """One value for a record: attrs[key], which must be the same kind of value as default.

    A class without the value, or with None, gets the default. A value the
    reader could not work out, or one of another kind, is reported.
    """
    value = attrs.get(key)
    if value is None:
        return default
    if is_unknown(value):
        problems.append("%s: could not read '%s'" % (where(module, class_name), key))
        return default
    if isinstance(default, bool):
        fits = isinstance(value, bool)
    elif isinstance(default, (int, float)):
        fits = isinstance(value, (int, float)) and not isinstance(value, bool)
    else:
        fits = isinstance(value, type(default))
    if not fits:
        problems.append("%s: '%s' is %s, which is not the kind of value the Wiki expects"
                        % (where(module, class_name), key, repr(value)[:60]))
        return default
    return value


def picture(attrs, key, module, class_name, problems):
    """The picture a value loads, as a path under the game's images folder. '' when the class has none."""
    value = attrs.get(key)
    if value is None:
        return ""
    if isinstance(value, dict) and "image" in value:
        return value["image"]
    problems.append("%s: could not read the picture '%s'" % (where(module, class_name), key))
    return ""


def reference(attrs, key, module, class_name, problems):
    """The class a value names, as 'module.Class'. '' when the class names none."""
    value = attrs.get(key)
    if value is None:
        return ""
    if isinstance(value, dict) and "ref" in value:
        return value["ref"]
    problems.append("%s: could not read '%s'" % (where(module, class_name), key))
    return ""


def named(values, field, module, class_name, problems):
    """The classes a list names, as 'module.Class', in order. Anything else in it is reported."""
    found = []
    if not isinstance(values, list):
        problems.append("%s: '%s' is not a list" % (where(module, class_name), field))
        return found
    for value in values:
        if isinstance(value, dict) and "ref" in value:
            found.append(value["ref"])
        else:
            problems.append("%s: '%s' holds something that is not a class" % (where(module, class_name), field))
    return found


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

        item_type = published(attrs, "type", "", module, name, problems)
        if item_type not in tab_of:
            problems.append("%s: its type %r is in no Bestiary tab" % (where(module, name), item_type))
            continue

        display = published(attrs, "name", add_spaces(name), module, name, problems)
        ability = reference(attrs, "ability", module, name, problems)
        if descends_from(module, name, "Elixir") and ability:
            # Elixir.__init__ writes the description from its ability's class
            # name, in a way the reader does not follow. This is what it writes.
            description = "Grants %s ability" % elixir_spacing(ability.split(".")[-1])
        else:
            description = published(attrs, "description", "", module, name, problems)
        if description.strip().lower() == display.strip().lower():
            report["placeholder_descriptions"].append(display)
            description = ""

        image = picture(attrs, "image", module, name, problems)
        if not image:
            problems.append("%s: has no icon" % where(module, name))

        ability_changes = {}
        if ability:
            as_set_up = setup_changes(modules, module, name, attrs, ability, problems)
            ability_changes = changes_to(modules, as_set_up, where(module, name), problems)

        records["items." + name] = {
            "name": display,
            "tab": tab_of[item_type],
            "type": item_type,
            "slot": published(attrs, "slot", "", module, name, problems),
            "arms": published(attrs, "idle_arms", "", module, name, problems),
            "description": description,
            "modifiers": published(attrs, "modifiers", {}, module, name, problems),
            "cost": published(attrs, "cost", 0, module, name, problems),
            "resource": published(attrs, "resource", "gold", module, name, problems),
            "ability": ability,
            "ability_changes": ability_changes,
            "grants_trait": reference(attrs, "grants_trait", module, name, problems),
            "cures": reference(attrs, "cures", module, name, problems),
            "brews_into": "",
            "image": image,
        }

    # items.brews: what an elixir vendor's cauldron turns each creature drop into.
    if "brews" not in module["values"]:
        problems.append("items.py no longer defines brews")
        return records
    context = {"modules": modules, "module": module, "attrs": {}, "locals": {}}
    recipes = evaluate(module["values"]["brews"], context)
    if not isinstance(recipes, dict) or is_unknown(recipes):
        problems.append("items.py: could not read brews")
        return records
    for ingredient in recipes:
        if ingredient not in records:
            problems.append("items.brews names %s, which is not published" % ingredient)
        else:
            made = reference(recipes, ingredient, module, ingredient.split(".")[1], problems)
            records[ingredient]["brews_into"] = made
    return records


def build_traits(modules, problems):
    module = modules["traits"]
    offerable = []
    if "OFFERABLE_TRAITS" in module["values"]:
        context = {"modules": modules, "module": module, "attrs": {}, "locals": {}}
        offerable = named(evaluate(module["values"]["OFFERABLE_TRAITS"], context), "OFFERABLE_TRAITS",
                          module, "Trait", problems)
    else:
        problems.append("traits.py no longer defines OFFERABLE_TRAITS")

    records = {}
    for name in module["order"]:
        if not descends_from(module, name, "Trait"):
            continue
        attrs = read_instance(modules, module, name)

        # A secret trait is left out, and never named in this public
        # repository. Only a plain False publishes a trait.
        secret = attrs.get("secret")
        if secret is not False:
            if secret is not True:
                problems.append("%s: could not read 'secret'" % where(module, name))
            continue

        image = picture(attrs, "image", module, name, problems)
        if not image:
            problems.append("%s: has no icon" % where(module, name))

        records["traits." + name] = {
            "name": published(attrs, "name", add_spaces(name), module, name, problems),
            "description": published(attrs, "description", "", module, name, problems),
            "modifiers": published(attrs, "scaling", {}, module, name, problems),
            "max_level": published(attrs, "max_level", 3, module, name, problems),
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

        stats = published(attrs, "stats", {}, module, name, problems)
        shown = {}
        for key in STAT_KEYS:
            if key not in stats:
                problems.append("%s: stats has no '%s'" % (where(module, name), key))
            else:
                shown[key] = stats[key]

        # The abilities in the order the Bestiary lists them, each as the mob built it.
        built = []
        for key in ["move", "default_ability"]:
            if reference(attrs, key, module, name, problems):
                built.append(attrs[key])
        special = published(attrs, "special_abilities", [], module, name, problems)
        if len(named(special, "special_abilities", module, name, problems)) == len(special):
            for one in special:
                built.append(one)

        abilities = []
        ability_changes = {}
        for one in built:
            abilities.append(one["ref"])
            changed = changes_to(modules, one, where(module, name), problems)
            if changed:
                if one["ref"] in ability_changes and ability_changes[one["ref"]] != changed:
                    problems.append("%s: changes two of its %s in different ways" % (where(module, name), one["ref"]))
                ability_changes[one["ref"]] = changed

        record = {
            "name": add_spaces(name),
            "group": group,
            "description": published(attrs, "description", "", module, name, problems),
            "stats": shown,
            "immunities": published(attrs, "immunities", [], module, name, problems),
            "abilities": abilities,
            "ability_changes": ability_changes,
            "drops": named(published(attrs, "loot", [], module, name, problems), "loot", module, name, problems),
            "drop_chance": published(attrs, "drop_chance", 0.5, module, name, problems),
            "image": "",
        }

        if group == "crewmate":
            portraits = []
            pool = published(attrs, "portrait_pool", {}, module, name, problems)
            for key in pool:
                for file_name in pool[key]:
                    portraits.append("portraits/" + file_name)
            if not portraits:
                problems.append("%s: has no portraits" % where(module, name))

            # A race's two lists of names can be one list (the Mer's): each name once.
            names = []
            pool = published(attrs, "name_pool", {}, module, name, problems)
            for key in pool:
                for person in pool[key]:
                    if person not in names:
                        names.append(person)

            # A race can be born with a secret trait. The game lists it nowhere
            # until an event reveals it, and it has no record, so it is left
            # out here as well.
            innate = []
            for pair in published(attrs, "innate_traits", [], module, name, problems):
                if not isinstance(pair, list) or len(pair) != 2 or not ref_of(pair[0]):
                    problems.append("%s: could not read an entry of 'innate_traits'" % where(module, name))
                elif ref_of(pair[0]) in trait_records:
                    innate.append({"trait": ref_of(pair[0]), "level": pair[1]})

            tiers = {}
            raw_tiers = published(attrs, "trait_tiers", {}, module, name, problems)
            for tier in raw_tiers:
                tiers[tier] = named(raw_tiers[tier], "trait_tiers", module, name, problems)

            record["portraits"] = portraits
            record["names"] = names
            record["hire_cost"] = published(attrs, "hire_cost", 0, module, name, problems)
            record["innate_traits"] = innate
            record["trait_tiers"] = tiers
            if portraits:
                record["image"] = portraits[0]
        else:
            cls = published(attrs, "cls", "", module, name, problems)
            if cls == "":
                problems.append("%s: has no 'cls', which names its sprite" % where(module, name))
            else:
                record["image"] = "mobs/mobs/%s_idle.png" % cls

        records["mobs." + name] = record
    return records


def build_factions(modules, rules, mob_records, problems):
    module = modules["factions"]
    records = {}
    for name in module["order"]:
        if not descends_from(module, name, "Faction"):
            continue
        attrs = read_instance(modules, module, name)
        display = published(attrs, "name", add_spaces(name), module, name, problems)
        if display in rules["not_factions"]:
            continue

        # Only the members the Bestiary lists as mobs are named.
        members = []
        listed = published(attrs, "members", [], module, name, problems)
        for found in named(listed, "members", module, name, problems):
            if found in mob_records:
                members.append(found)

        # Only a herald's name is published, so what the herald is need not be readable.
        heralds = []
        raw_heralds = attrs.get("heralds")
        if isinstance(raw_heralds, dict) and "unknown" not in raw_heralds:
            for key in raw_heralds:
                heralds.append(add_spaces(key))
        elif raw_heralds is not None:
            problems.append("%s: could not read 'heralds'" % where(module, name))

        # A faction names its sites by their class names in locations.py.
        sites = []
        for site in published(attrs, "sites", [], module, name, problems):
            if isinstance(site, str):
                sites.append("locations." + site)
            else:
                problems.append("%s: 'sites' holds something that is not a name" % where(module, name))

        records["factions." + name] = {
            "name": display,
            "description": published(attrs, "description", "", module, name, problems),
            "members": members,
            "heralds": heralds,
            "sites": sites,
            "ally": published(attrs, "ally", "", module, name, problems),
            "enemy": published(attrs, "enemy", "", module, name, problems),
            "image": picture(attrs, "banner", module, name, problems),
        }
    return records


def build_locations(modules, faction_records, problems):
    """The places a crew trades at, and the sites a faction's crews point out.

    The Bestiary has no tab for locations, so the rule is the extract's own: a
    location is published if its window is the market window (gui.Location),
    or if a published faction lists it among its sites. That leaves out the
    huts, nests, ruins, chests and gathering spots, and the tutorial.
    """
    module = modules["locations"]
    sites = {}
    for key in faction_records:
        for site in faction_records[key]["sites"]:
            sites[site.split(".")[1]] = True

    records = {}
    for name in module["order"]:
        if not descends_from(module, name, "Location"):
            continue
        attrs = read_instance(modules, module, name)
        if ref_of(attrs.get("gui")) != "gui.Location" and name not in sites:
            continue

        display = add_spaces(name)
        description = published(attrs, "description", "", module, name, problems)
        if description.strip().lower() == display.lower():
            description = ""

        # What it is drawn with on the map: a four-frame strip, or one picture.
        strip = False
        animations = attrs.get("animations")
        if isinstance(animations, dict) and "idle" in animations:
            drawn = picture(animations, "idle", module, name, problems)
            strip = True
        else:
            drawn = picture(attrs, "image", module, name, problems)
        if drawn == "":
            problems.append("%s: has no picture" % where(module, name))

        # What it sells. A faction's place lists its wares in tiers, one for
        # each status the buyer must hold (items.stock); an elixir vendor has
        # one list that anyone can buy from.
        sells = []
        if attrs.get("wares") is not None:
            for tier in published(attrs, "wares", [], module, name, problems):
                sells.append(named(tier, "wares", module, name, problems))
        elif attrs.get("selling") is not None:
            sells.append(named(published(attrs, "selling", [], module, name, problems), "selling",
                               module, name, problems))

        # A place can keep two hands of one race for hire: each race once.
        hires = []
        recruits = published(attrs, "recruits", [], module, name, problems)
        for found in named(recruits, "recruits", module, name, problems):
            if found not in hires:
                hires.append(found)

        records["locations." + name] = {
            "name": display,
            "description": description,
            "faction": reference(attrs, "faction", module, name, problems),
            "sells": sells,
            "buys": published(attrs, "buying", "", module, name, problems),
            "hires": hires,
            "brews": attrs.get("brews") is not None,
            "scene": picture(attrs, "scene", module, name, problems),
            "image": drawn,
            "strip": strip,
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


def ability_record(modules, name, attrs, problems):
    """An ability's record, from the values one of its instances carries."""
    module = modules["abilities"]
    return {
        "name": add_spaces(name),
        "description": published(attrs, "description", "", module, name, problems),
        "type": published(attrs, "type", "", module, name, problems),
        "damage_type": published(attrs, "damage_type", "", module, name, problems),
        "base_stats": published(attrs, "base_stats", {}, module, name, problems),
        "stamina_cost": published(attrs, "stamina_cost", 0, module, name, problems),
        "mana_cost": published(attrs, "mana_cost", 0, module, name, problems),
        "status_effects": status_effects_of(modules, name, attrs),
        "image": picture(attrs, "image", module, name, problems),
    }


def build_abilities(modules, wanted, problems):
    """Only abilities that a published item or mob refers to are published."""
    module = modules["abilities"]
    records = {}
    for reference in wanted:
        name = reference.split(".")[1]
        if name not in module["classes"]:
            problems.append("abilities.py has no class named %s, which something refers to" % name)
            continue
        records[reference] = ability_record(modules, name, read_instance(modules, module, name), problems)
    return records


def changes_to(modules, built, owner, problems):
    """How an item or mob's own ability differs from the ability's record.

    The Bestiary shows an ability as its owner has changed it (the Musket's
    damage, range and stamina). built is the ability as the reader holds it,
    with those changes kept on it. Returns the record's values that differ;
    of base_stats, only the stats that differ.
    """
    name = built["ref"].split(".")[1]
    if "changes" not in built or name not in modules["abilities"]["classes"]:
        return {}
    attrs = read_instance(modules, modules["abilities"], name)
    plain = ability_record(modules, name, attrs, [])
    found = []
    used = ability_record(modules, name, apply_changes(attrs, built["changes"]), found)
    for problem in found:
        problems.append("%s: after its changes to the ability, %s" % (owner, problem))

    differing = {}
    for key in used:
        if used[key] == plain[key]:
            continue
        if key == "base_stats":
            differing[key] = {}
            for stat in used[key]:
                if stat not in plain[key] or used[key][stat] != plain[key][stat]:
                    differing[key][stat] = used[key][stat]
        else:
            differing[key] = used[key]
    return differing


def setup_changes(modules, module, class_name, attrs, ability, problems):
    """An item's ability as its setup_ability method leaves it: built, with the changes kept on it."""
    built = {"ref": ability}
    chain = parents_first(module, class_name)
    chain.reverse()
    method = None
    for name in chain:
        if method is None:
            method = module["classes"][name]["methods"].get("setup_ability")
    if method is None or len(method.args.args) != 2:
        return built

    context = {"modules": modules, "module": module, "attrs": attrs, "locals": {method.args.args[1].arg: built}}
    for statement in method.body:
        if isinstance(statement, ast.Pass):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue
        if not follow(statement, context):
            problems.append("%s.py line %d (class %s): setup_ability does something the reader does not follow"
                            % (module["name"], statement.lineno, class_name))
    return built


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
        if attrs.get("duration") is False:
            # Latched: it has no count of turns, and stays until something removes it.
            attrs["duration"] = 0
        records[reference] = {
            "name": add_spaces(name),
            # The word a mob's immunities list uses for this effect.
            "key": published(attrs, "name", "", module, name, problems),
            "description": published(attrs, "description", "", module, name, problems),
            "duration": published(attrs, "duration", 0, module, name, problems),
            "image": picture(attrs, "icon", module, name, problems),
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
    locations = build_locations(modules, factions, problems)

    wanted_abilities = []
    for key in items:
        if items[key]["ability"]:
            wanted_abilities.append(items[key]["ability"])
    for key in mobs:
        for reference in mobs[key]["abilities"]:
            wanted_abilities.append(reference)
    abilities = build_abilities(modules, sorted_unique(wanted_abilities), problems)

    # The status effects an ability applies, as it is and as an item or mob changes it.
    wanted_effects = []
    for key in abilities:
        for found in abilities[key]["status_effects"]:
            wanted_effects.append(found)
    for key in items:
        for found in items[key]["ability_changes"].get("status_effects", []):
            wanted_effects.append(found)
    for key in mobs:
        for changed in mobs[key]["ability_changes"]:
            for found in mobs[key]["ability_changes"][changed].get("status_effects", []):
                wanted_effects.append(found)
    effects = build_effects(modules, sorted_unique(wanted_effects), problems)
    check_references(modules, [items, traits, mobs, factions, locations, abilities, effects], problems)

    constants = modules["constants"]
    meta = {"version": "", "storm_interval": 0}
    if "VERSION" in constants["values"]:
        meta["version"] = ast.literal_eval(constants["values"]["VERSION"])
    if "STORM_INTERVAL" in constants["values"]:
        meta["storm_interval"] = ast.literal_eval(constants["values"]["STORM_INTERVAL"])

    # The gems a cauldron asks for on top of the drop it brews (see items.brews).
    if "Location" not in modules["gui"]["classes"]:
        problems.append("gui.py no longer has a class named Location")
    else:
        shop = read_instance(modules, modules["gui"], "Location")
        meta["brew_cost"] = published(shop, "brew_cost", 0, modules["gui"], "Location", problems)

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
        "locations.json": locations,
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
    """The text of one file in game/data.

    Records are written in alphabetical order, so moving a class within the
    game's source changes nothing here. Inside a record the order is the
    game's: the Bestiary draws an item's bonuses in the order its class lists them.
    """
    ordered = {}
    keys = list(records.keys())
    keys.sort()
    for key in keys:
        ordered[key] = records[key]
    return json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"


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
    lines.append("traits %d, abilities %d, status effects %d, factions %d, locations %d"
                 % (len(data["traits.json"]), len(data["abilities.json"]),
                    len(data["effects.json"]), len(data["factions.json"]), len(data["locations.json"])))
    lines.append("%d mobs have no description; %d items have a description that only repeats their name"
                 % (len(report["mobs_without_description"]), len(report["placeholder_descriptions"])))
    return lines
