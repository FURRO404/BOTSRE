import asyncio
import csv
import io
import logging
import re
import string
from io import StringIO

import aiofiles

from src_send.WtFileUtils.vromfs.VROMFs import VROMFs

# lang_dir.dump_files("lang")

import os


v = VROMFs("char.vromfs.bin").get_directory()
f1 = v["config"]["unittags.blk"].get_data()["root"]
def get_unit_info(internal_name):
    internal_data = f1[internal_name]
    tags = list(internal_data["tags"].keys())
    if internal_data.get("type", None) == "helicopter":
        tags += ["type_helicopter"]
    for key in tags:
        match key:
            case "type_spaa":
                return "SPAA"
            case "type_light_tank":
                return "Light Tank"
            case "type_heavy_tank":
                return "Tank"
            case "type_medium_tank":
                return "Tank"
            case "type_fighter":
                return "Fighter"
            case "type_bomber":
                return "Bomber"
            case "type_helicopter":
                return "Helicopter"
    print(f"ERROR DETERMING VEHICLE TYPE FOR UNIT: {internal_name} WITH TAGS: {tags}")

def get_unit_info_abrev(internal_name):
    internal_data = f1[internal_name]
    tags = list(internal_data["tags"].keys())
    if internal_data.get("type", None) == "helicopter":
        tags += ["type_helicopter"]
    for key in tags:
        match key:
            case "type_spaa":
                return "AA"
            case "type_light_tank":
                return "L"
            case "type_heavy_tank":
                return "T"
            case "type_medium_tank":
                return "T"
            case "type_fighter":
                return "F"
            case "type_bomber":
                return "B"
            case "type_helicopter":
                return "H"
    print(f"ERROR DETERMING VEHICLE TYPE FOR UNIT: {internal_name} WITH TAGS: {tags}")

def get_dict_from_list(internal_name_list):
    payload = {}
    for name in internal_name_list:
        t = get_unit_info_abrev(name)
        if t in payload:
            payload[t] += 1
        else:
            payload[t] = 1
    return payload

class LangTableReader:
    lang_dir = VROMFs("lang.vromfs.bin").get_directory() 
    file = lang_dir["lang"]["units.csv"]
    z = csv.reader(StringIO(file.get_data().decode('utf-8')), delimiter=';')
    global_data = {}
    header_info = z.__next__()[1:]
    for line in z:
        global_data.update({line[0]: line[1:]})
        
    def __init__(self, language):
        self.index = 0 # defaults to english
        self.update_langauge(language)
        #logging.info(f"Language set to {self.index} with value {language}")


    def update_langauge(self, lang):
        if lang in self.header_info:
            self.index = self.header_info.index(lang)
            return True
        return False

    def get_translate(self, value):
        #logging.info(f"translating value {value} into {LangTableReader.header_info[self.index]}")
        val = LangTableReader.global_data[value][self.index]
        val = val.replace("\\t", "\t")
        return val
        
# with open("temp.txt", "w") as f:
#     for x, y in internal_to_name.items():
#         f.write(f"{x} : {y}\n")
# print(internal_to_name.keys())
# print(internal_to_name["hunter_f58_switzerland_shop"])
# print([[x.split(";")] for x in csv_file.split("\n")][0])

def normalize_name(name: str) -> str:
    name = name.replace('_', ' ')
    allowed_punct = re.escape(string.punctuation)
    pattern = f'[^A-Za-z0-9{allowed_punct} ]'
    # Remove characters that don't match the allowed set
    normalized = re.sub(pattern, '', name)
    return normalized

# vehicle = "germ_pzkpfw_VI_ausf_h1_tiger_west"
# print(asyncio.run(match_cdk_to_actual_name(vehicle)))