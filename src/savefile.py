import os
import time
import re
from pathlib import Path
import datasheets
import win32con
import win32gui
import win32api
import win32process


def endian_turn(hex_string: str) -> str:
    """
    Turns little-endian hex string to big-endian or visa versa.
    Example: 8097FA01 <-> 01FA9780
    """

    if len(hex_string) < 2:
        return hex_string

    if len(hex_string) % 2 == 1:
        return hex_string

    pairs = [hex_string[i:i + 2] for i in range(0, len(hex_string), 2)]

    return ''.join(reversed(pairs))


def item_id_from_dec_to_hex(item_id: str, max_length: int) -> str:
    """
    Turns decimal item id to hex version that's can be searched in save file.
    Example: 16000000 -> 0024f400
    """

    hex_big_endian = hex(int(item_id))[2:]
    if len(hex_big_endian) % 2 == 1:
        hex_big_endian = '0' + hex_big_endian
    hex_little_endian = endian_turn(hex_big_endian)
    hex_little_endian += (max_length - len(hex_little_endian)) * '0'

    return hex_little_endian


def add_escaping_symbols_to_byte_reg(reg_expression: bytes) -> bytes:
    """
    Adding escaping symbols to regular expression so it can be
    performed on byte strings.
    """

    escaping_characters = [b'\\', b'[', b']', b'(', b')', b'|',
                           b'^', b'$', b'.', b'?', b'*', b'+']
    for ch in escaping_characters:
        reg_expression = reg_expression.replace(ch, b'\\' + ch)

    return reg_expression

class SaveFile:

    def __init__(self , location: str):

        self.location = location
        self.saveslots: list = []
        self.current_saveslot: SaveSlot = ''
        self.font_size_adjustment: int = -1
        self.standard_pause_time: int = 0
        self.recovery_hotkey: str = ''
        self.recovery_hotkey_ctrl: bool = False
        self.recovery_hotkey_shift: bool = False
        self.recovery_hotkey_alt: bool = False
        self.journal: list = []
        self.window_scale: float = 1.3

        self.game_controls: dict = {'': ''}
        for key in self.control_keys_ranges().keys():
            self.game_controls[key] = ''

        # If "online_mode" is on, then Melina's Fingers will stop some macros
        # from performing to not harm balanced PvP.
        self.safe_online_mode: bool = True
        self.safe_online_mode_last_check_time = time.time()


    @staticmethod
    def range_before_saveslots() -> int:
        """
        Returns an amount of symbols in HEX-save-file that goes before
        first save-slot information starts.
        """

        return 0x0000310

    @staticmethod
    def slot_ranges(savenumber: int = 0) -> tuple | list:
        """
        Returns hex interval for the save slot in save file.
        If save number is 0, returns a list of all 10 intervals.
        """

        between_slots = 16
        saveslot_width = 2621456

        intervals = [(SaveFile.range_before_saveslots(), 0x0280310)]  # First save file.
        for _ in range(9):
            last_interval = intervals[-1]
            new_interval_begin = last_interval[1] + between_slots
            new_interval_end = last_interval[1] + saveslot_width
            intervals.append((new_interval_begin, new_interval_end))

        if savenumber == 0:
            return intervals
        else:
            return intervals[savenumber - 1]

    def calculate_online_mode(self) -> None:
        """
        Calculates 'online_mode' attribute.
        If it's True, Melina's Fingers will have restrictions in its
        functionality to not harm PvP.
        """

        self.safe_online_mode_last_check_time = time.time()

        def elden_ring_pid(hwnd, game_pid_list: list) -> None:
            """
            Append process id for opened Elden Ring window to 'game_pid_list'
            if Elden Ring is open.
            """

            if len(game_pid_list):
                return

            try:
                class_name = win32gui.GetClassName(hwnd).lower()
            except:
                return

            is_elden_ring = False
            if 'elden' in class_name and 'ring' in class_name \
                    and len(class_name) < 15:
                is_elden_ring = True

            if not is_elden_ring:
                return

            process_id = win32process.GetWindowThreadProcessId(hwnd)[1]

            game_pid_list.append(process_id)

        game_pid_list = []
        win32gui.EnumWindows(elden_ring_pid, game_pid_list)

        # If Elden Ring in not open, set "False" to not restrict testing.
        if not game_pid_list:
            self.safe_online_mode = False
            self.make_journal_entry(f'"Safe online mode" is calculated '
                                    f'and set to "{self.safe_online_mode}".')
            return

        game_pid = game_pid_list[0]

        # If we can get a list of modules from Elden Ring process, it means
        # that EAC in turned off, and we can set safe online mode to False.
        # But if this attempt raises an exception, it means taht EAC is on, and
        # we must set safe online mode to True.
        try:
            handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                0, game_pid)
            self.safe_online_mode = False
            modlist = win32process.EnumProcessModules(handle)
        except:
            self.safe_online_mode = True

        self.make_journal_entry(f'"Safe online mode" is calculated '
                                f'and set to "{self.safe_online_mode}".')

    def get_slot_names(self) -> list:
        """
        Returns a list of slot names, getting them directly from save flie.
        """
        with open(self.location, "rb") as f:
            data = f.read()

        names_ranges = SaveFile.slot_names_ranges()
        names = [data[begin:end].decode('utf-16') for begin, end in names_ranges]
        names = list(map(lambda x: x.strip('\x00'), names))

        return names

    @staticmethod
    def slot_names_ranges() -> tuple:
        """
        Returns HEX-ranges of places in save-file that keeps save slot names
        (characters names).
        """

        return ((0x1901d0e, 0x1901d0e + 32),
                (0x1901f5a, 0x1901f5a + 32),
                (0x19021a6, 0x19021a6 + 32),
                (0x19023f2, 0x19023f2 + 32),
                (0x190263e, 0x190263e + 32),
                (0x190288a, 0x190288a + 32),
                (0x1902ad6, 0x1902ad6 + 32),
                (0x1902d22, 0x1902d22 + 32),
                (0x1902f6e, 0x1902f6e + 32),
                (0x19031ba, 0x19031ba + 32))

    def fill_saveslots(self):
        """
        Fills the saveslots list in savefile, naming and numerating them.
        """

        self.saveslots.clear()
        if self.location:
            names = self.get_slot_names()
            for i, name in enumerate(names, 1):
                if name:
                    saveslot = SaveSlot()
                    saveslot.number = i
                    saveslot.name = name
                    saveslot.savefile = self
                    self.saveslots.append(saveslot)

    def read_game_controls(self):
        """
        Reads game controls from save-file and put it to 'game_controls'
        attribute to be used by macros.
        """

        for key in self.game_controls.keys():
            self.game_controls[key] = ''

        if self.location == '':
            return

        slot_data = self.get_data()

        control_keys = self.control_keys_ranges()
        control_keys_values = self.control_keys_values()
        for key, value in control_keys.items():
            hex_string = slot_data[value:value + 1]
            control_keys[key] = int(hex_string.hex(), 16)
            control_keys[key] = control_keys_values.get(control_keys[key], '')
            self.game_controls[key] = control_keys[key]

    @staticmethod
    def control_keys_ranges() -> dict:
        """
        Returns HEX-ranges of places in save-file that keeps controls for some
        actions that could be used in macros.
        """

        return {
            'move_up': 0x019034dd,
            'move_down': 0x019034f1,
            'move_left': 0x01903505,
            'move_right': 0x01903519,
            'roll': 0x01903541,
            'jump': 0x01903555,
            'crouch': 0x0190352d,
            'reset_camera': 0x019035b9,
            'switch_spell': 0x019035cd,
            'switch_item': 0x019035e1,
            'attack': 0x0190361d,
            'strong_attack': 0x01903631,
            'guard': 0x01903645,
            'skill': 0x01903659,
            'use_item': 0x0190366d,
            'event_action': 0x01903681,
        }

    @staticmethod
    def control_keys_values() -> dict:
        """
        Returns values for keys that are used in save-file to define what key
        is used for a control. Values are in decimal.
        For example, "Num4" ("144" dec.) would be "90" in HEX-file.
        """

        return {
            128: 'F1',
            129: 'F2',
            130: 'F3',
            131: 'F4',
            132: 'F5',
            133: 'F6',
            134: 'F7',
            135: 'F8',
            136: 'F9',
            137: 'F10',
            156: 'F11',
            157: 'F12',
            80: '0',
            71: '1',
            72: '2',
            73: '3',
            74: '4',
            75: '5',
            76: '6',
            77: '7',
            78: '8',
            79: '9',
            151: 'Num0',
            148: 'Num1',
            149: 'Num2',
            150: 'Num3',
            144: 'Num4',
            145: 'Num5',
            146: 'Num6',
            140: 'Num7',
            141: 'Num8',
            142: 'Num9',
            99: 'A',
            117: 'B',
            115: 'C',
            101: 'D',
            87: 'E',
            102: 'F',
            103: 'G',
            104: 'H',
            92: 'I',
            105: 'J',
            106: 'K',
            107: 'L',
            119: 'M',
            118: 'N',
            93: 'O',
            94: 'P',
            85: 'Q',
            88: 'R',
            100: 'S',
            89: 'T',
            91: 'U',
            116: 'V',
            86: 'W',
            114: 'X',
            90: 'Y',
            113: 'Z',
            84: 'Tab',
            111: 'Shift',
            123: 'Shift',
            98: 'Ctrl',
            226: 'Ctrl',
            83: 'Backspace',
            126: 'Space',
            97: 'Enter',
            225: 'Enter',
            125: 'Alt',
            268: 'Home',
            188: 'PageUp',
            194: 'End',
            196: 'PageDown',
            197: 'Insert',
            198: 'Delete',
            190: 'Up',
            192: 'Left',
            195: 'Down',
            193: 'Right'
        }

    def is_empty(self) -> bool:
        """
        Checks does the savefile has some macros in it.
        """

        for saveslot in self.saveslots:
            if saveslot.macros:
                return False

        return True

    def calculate_savefile_location(self) -> None:
        r"""
        Tries to find a save-file location and returns a path to it.
        Standard save file location:
        C:\Users\{Username}\AppData\Roaming\EldenRing\{SteamID}\ER0000.sl2
        """

        elden_ring_files_path = str(Path.home()) + '\\AppData\\Roaming\\EldenRing'

        if not os.path.exists(elden_ring_files_path):
            return

        # Looking for a folder with a name like "7xxxxxxxxxxxxxxxx"
        steam_id_folder = ''
        file_names = os.listdir(elden_ring_files_path)
        for file_name in file_names:
            if len(file_name) > 10 and file_name.startswith('7') \
                    and file_name.isdigit():
                steam_id_folder = file_name
                break

        if not steam_id_folder:
            return

        savefile_location = f'{elden_ring_files_path}\\{steam_id_folder}\\ER0000.sl2'

        if not os.path.exists(savefile_location):
            return

        self.location = savefile_location

    def get_data(self) -> bytes:
        """
        Returns hex data of save file.
        """

        with open(self.location, "rb") as f:
            data = f.read()
            return data

    def make_journal_entry(self, entry: str) -> None:
        """
        Makes an entry to journal that can be seen on "Journal" page.
        """

        # Keeping journal at adequate length.
        while len(self.journal) > 500:
            self.journal.pop(0)

        entry_time = time.strftime('%Y.%m.%d %H:%M:%S')
        entry_as_tuple = entry_time, entry

        # For developer.
        print(*entry_as_tuple)

        self.journal.append(entry_as_tuple)

class SaveSlot:

    def __init__(self):

        self.id: int = 0
        self.number: int = 0
        self.name: str = ''
        self.savefile = SaveFile('')
        self.macros: list = []
        self.weapons: list = []
        self.weapons_manual: list = []
        self.weapons_manual_mode: bool = False
        self.armor_head: list = []
        self.armor_head_manual: list = []
        self.armor_head_manual_mode: bool = False
        self.armor_chest: list = []
        self.armor_chest_manual: list = []
        self.armor_chest_manual_mode: bool = False
        self.armor_arms: list = []
        self.armor_arms_manual: list = []
        self.armor_arms_manual_mode: bool = False
        self.armor_legs: list = []
        self.armor_legs_manual: list = []
        self.armor_legs_manual_mode: bool = False
        self.talismans: list = []
        self.talismans_manual: list = []
        self.talismans_manual_mode: bool = False
        self.spells: list = []
        self.items: list = []
        self.current_spell: int = 0
        self.current_item: int = 0
        self.search_mode_magic: str = 'auto'
        self.search_mode_equipment: str = 'auto'
        self.search_mode_items: str = 'auto'
        self.current_equipment_type = 'Armament'
        self.current_equipment = {'weapon_right_1': 0,
                                  'weapon_right_2': 0,
                                  'weapon_right_3': 0,
                                  'weapon_left_1': 0,
                                  'weapon_left_2': 0,
                                  'weapon_left_3': 0,
                                  'armor_head': 0,
                                  'armor_chest': 0,
                                  'armor_arms': 0,
                                  'armor_legs': 0,
                                  'talisman_1': 0,
                                  'talisman_2': 0,
                                  'talisman_3': 0,
                                  'talisman_4': 0}

    def get_slot_data(self) -> bytes:
        """
        Returns hex data of save file related to specific save slot.
        Returns full data of save file is safe slot is not specified.
        :return:
        """
        with open(self.savefile.location, "rb") as fh:
            data = fh.read()

            # if not savenumber:
            #     return data

            slot_interval = SaveFile.slot_ranges(self.number)
            return data[slot_interval[0]:slot_interval[1]]


    @staticmethod
    def inventory_and_chest_separator() -> bytes:
        """
        Returns a HEX-string that separates inventory and chest block for
        equipment searching.
        """

        return bytes.fromhex('ffffffff00000000') * 4

    def instances_search_range(self) -> tuple:
        """
        Seeks for a range in which can be found instances of equipment in specific
        save slot data. Minimal range is a position of slot data name.
        Max range can't be calculated and is taken with a margin.
        """

        slot_data = self.get_slot_data()
        slot_name = self.name

        slot_name_hex = bytes(slot_name, 'utf-8')
        slot_name_hex_bytes = [bytes.fromhex(hex(x)[2:]) for x in slot_name_hex]
        slot_name_hex_bytes = [x + bytes.fromhex('00') for x in
                               slot_name_hex_bytes]
        slot_name_hex = b''.join(slot_name_hex_bytes)

        slot_name_position = slot_data.find(slot_name_hex)

        range_max = 0x00035000

        return slot_name_position, range_max

    def get_equipment(self, equipment_type: str = '') -> None:
        """
        Gets lists of weapons, armor, talismans and spell and fills it
        in saveslot's respective attributes.
        """

        # Lists to refill.
        self.weapons = []
        self.armor_head = []
        self.armor_chest = []
        self.armor_arms = []
        self.armor_legs = []
        self.talismans = []
        self.spells = []
        self.items = []

        savefile_path = self.savefile.location

        if not savefile_path:
            return

        slot_data = self.get_slot_data()

        # Looking for all equipment mentioned in save-file, whatever quantity
        # and position in inventory or chest.
        slot_data_for_equipment_search = slot_data[:0x00030000]
        all_equipment_having = []
        for weapon in datasheets.weapons():
            weapon_id = weapon[1]
            weapon_name = weapon[2]

            if bytes.fromhex(weapon_id) in slot_data_for_equipment_search:
                all_equipment_having.append([weapon_name, weapon_id, 'weapons'])

        for armor in datasheets.armor():
            armor_id = armor[1]
            armor_name = armor[2]
            if bytes.fromhex(armor_id) in slot_data_for_equipment_search:
                all_equipment_having.append([armor_name, armor_id, 'armor'])

        # Looking for many instances of each equipment. In save-file structure
        # is like this: [inventory instances]-[separator]-[chest instances]
        # We need only inventory instances, so first we need to find the separator.

        instances_range = self.instances_search_range()
        data_for_instances_search = slot_data[instances_range[0]:
                                              instances_range[1]]
        separator = self.inventory_and_chest_separator()
        separator_pos = data_for_instances_search.rfind(separator)

        inventory_list = []
        for equipment in all_equipment_having:

            equipment_name = equipment[0]
            equipment_id = equipment[1]
            equipment_type = equipment[2]
            equipment_mark = '8080'
            if equipment_type == 'armor':
                equipment_mark = '8090'

            # In save-file we're looking for lines like: ID ID 80 MM WW WW WW (WW)
            # Where:
            #   ID ID - ID of specific instance of equipment.
            #   80 MM - mark of equipment. "80 80" for weapon, "80 90" for armor.
            #   WW WW WW (WW) - equipment ID. Weapon has 4 pieces, armor has 3.
            # Each line represents an instance of equipment.
            id_for_reg = bytes.fromhex(equipment_mark + equipment_id)
            id_for_reg = add_escaping_symbols_to_byte_reg(id_for_reg)

            reg_expression = b'.{2}(?=' + id_for_reg + b')'
            result = re.finditer(reg_expression,
                                 slot_data[:instances_range[0] + separator_pos])

            for match in result:

                instance_id = match.group() + bytes.fromhex(equipment_mark)
                instance_position = data_for_instances_search.rfind(instance_id)
                if instance_position < 0:
                    continue

                # As we found instance's ID, we can see, in what part this ID
                # is located. If it's in inventory part, then that's it.
                if instance_position > separator_pos:
                    continue

                instance_id = instance_id.hex(' ').replace(' ', '')
                position_in_file = hex(instances_range[0]
                                       + instance_position
                                       + SaveFile.range_before_saveslots())

                # We have to learn in what order equipment is placed in inventory
                # if inventory is sorted as "Ascending Order of Acquisition".
                # Instance's ID is located in line that looks like:
                # ID ID 80 80 XX XX XX XX NN NN
                # Where:
                #   ID ID - instance's ID
                #   80 80 XX XX XX XX - not interesting data
                #   NN NN - additional ID that can be used to learn what order in
                #           inventory this instance has if inventory is sorted as
                #           "Ascending Order of Acquisition".
                inventory_order_id = data_for_instances_search[
                                     instance_position + 8:
                                     instance_position + 10]
                inventory_order_id = inventory_order_id.hex(' ').replace(' ', '')

                # Order ID has two HEX numbers ("f1 21") but actual order goes
                # on mirrored numbers ("21 f1", "21 f2", "21 f3" etc.)
                inventory_order_id = inventory_order_id[2:4] + \
                                     inventory_order_id[:2]

                # We need to check what type of armor an instance has.
                if equipment_type == 'armor':
                    equipment_id_decimal = str(int(endian_turn(equipment_id), 16))
                    if equipment_id_decimal.endswith('000'):
                        equipment_type += '_head'
                    elif equipment_id_decimal.endswith('100'):
                        equipment_type += '_chest'
                    elif equipment_id_decimal.endswith('200'):
                        equipment_type += '_arms'
                    elif equipment_id_decimal.endswith('300'):
                        equipment_type += '_legs'

                instance_dict = {}
                instance_dict.setdefault('type', equipment_type)
                instance_dict.setdefault('name', equipment_name)
                instance_dict.setdefault('id', equipment_id)
                instance_dict.setdefault('instance_id', instance_id)
                instance_dict.setdefault('order_in_file', inventory_order_id)
                instance_dict.setdefault('position_in_file', position_in_file)
                inventory_list.append(instance_dict)

        # Talismans are located in save-file simmilar to armor and weapons, but
        # not identical.
        # Talisman line looks like: XX XX 00A001000000 NN NN, where
        #   XX XX - talisman ID.
        #   00A001000000 - always identical part
        #   NN NN - order ID.
        #
        # Inventory/Chest search is identical to weapons and armor.
        # Talismans don't have instances, you can only have one.
        talisman_mark = '00A001000000'
        for talisman in datasheets.talismans():
            talisman_id = talisman[1]
            talisman_name = talisman[2]

            talisman_search = bytes.fromhex(talisman_id + talisman_mark)
            talisman_position = data_for_instances_search.find(talisman_search)
            if talisman_position < 0:
                continue

            if talisman_position > separator_pos:
                continue

            position_in_file = hex(instances_range[0]
                                   + talisman_position
                                   + SaveFile.range_before_saveslots())

            inventory_order_id = data_for_instances_search[
                                 talisman_position + 8:
                                 talisman_position + 10]
            inventory_order_id = inventory_order_id.hex(' ').replace(' ', '')
            inventory_order_id = inventory_order_id[2:4] + inventory_order_id[:2]

            instance_dict = {}
            instance_dict.setdefault('type', 'talismans')
            instance_dict.setdefault('name', talisman_name)
            instance_dict.setdefault('id', talisman_id)
            instance_dict.setdefault('instance_id', '')
            instance_dict.setdefault('order_in_file', inventory_order_id)
            instance_dict.setdefault('position_in_file', position_in_file)
            inventory_list.append(instance_dict)

        # Chosen spells can be found pretty easily.
        # Spell line looks like SS SS 00 00 FF FF
        # Where:
        #   SS SS - spell ID
        #   00 00 FF FF - mark of chosen spell
        # In save-file these lines are in order identical to order in game.
        for spell in datasheets.spells():
            spell_id = spell[1]
            spell_name = spell[2]
            spell_mark = '0000FFFF'
            spell_search = bytes.fromhex(spell_id + spell_mark)

            spell_position = data_for_instances_search.find(spell_search)
            if spell_position < 0:
                continue

            position_in_file = hex(instances_range[0]
                                   + spell_position
                                   + SaveFile.range_before_saveslots())

            inventory_order_id = position_in_file[2:]

            instance_dict = {}
            instance_dict.setdefault('type', 'spells')
            instance_dict.setdefault('name', spell_name)
            instance_dict.setdefault('id', spell_id)
            instance_dict.setdefault('instance_id', '')
            instance_dict.setdefault('order_in_file', inventory_order_id)
            instance_dict.setdefault('position_in_file', position_in_file)
            inventory_list.append(instance_dict)

        # To find items in quick slots we need to find first "46 41 43 45"
        # sequience in safe-file ("FACE", don't know what that means).
        # End of quick slots will be 88 symbols earlier.
        #
        # Quick slots are just sequence of ten "XX XX XX XX"-like words, where
        # XX XX XX XX is item ID.
        #
        # In save-file these lines are in order identical to order in game.
        face_search = bytes.fromhex('46414345')
        face_pos = slot_data_for_equipment_search.find(face_search)
        if face_pos:
            items_datasheet = datasheets.items()
            items_line = slot_data_for_equipment_search[face_pos-44-40:face_pos-44]
            for i in range(10):
                item_hex = items_line[i*4:i*4+2]
                item_search = item_hex.hex(' ').replace(' ', '')

                item_name = next((x[2] for x in items_datasheet if x[1] == item_search), None)
                if item_name is None:
                    item_name = ''

                item_dict = {}
                item_dict.setdefault('type', 'items')
                item_dict.setdefault('name', item_name)
                item_dict.setdefault('id', item_search)
                item_dict.setdefault('order_in_file', str(i))
                inventory_list.append(item_dict)

        sorted_equipment = sorted(inventory_list, key=lambda x: (x['type'],
                                                  int(x['order_in_file'], 16)))

        fields_accordance = {
            'weapons': self.weapons,
            'armor_head': self.armor_head,
            'armor_chest': self.armor_chest,
            'armor_arms': self.armor_arms,
            'armor_legs': self.armor_legs,
            'talismans': self.talismans,
            'spells': self.spells,
            'items': self.items,
        }

        for equipment in sorted_equipment:
            fields_accordance[equipment['type']].append(equipment)
