import asyncio
import csv
import io
import re
import string

import aiofiles

from src_send.WtFileUtils.vromfs.VROMFs import VROMFs


lang_dir = VROMFs("lang.vromfs.bin").get_directory() 
# lang_dir.dump_files("lang")
csv_file = lang_dir["lang"]["units.csv"].get_data().decode("utf-8")
internal_to_name = {y[0][1:-1]: y[1][1:-1] for y in [x.split(";") for x in csv_file.split("\n")] if len(y) > 2}
# with open("temp.txt", "w") as f:
#     for x, y in internal_to_name.items():
#         f.write(f"{x} : {y}\n")
# print(internal_to_name.keys())
# print(internal_to_name["hunter_f58_switzerland_shop"])
# print([[x.split(";")] for x in csv_file.split("\n")][0])

async def match_cdk_to_actual_name(vehicle_name):
    return normalize_name(internal_to_name[vehicle_name+"_shop"])


def normalize_name(name: str) -> str:
    name = name.replace('_', ' ')
    allowed_punct = re.escape(string.punctuation)
    pattern = f'[^A-Za-z0-9{allowed_punct} ]'
    # Remove characters that don't match the allowed set
    normalized = re.sub(pattern, '', name)
    return normalized

# vehicle = "germ_pzkpfw_VI_ausf_h1_tiger_west"
# print(asyncio.run(match_cdk_to_actual_name(vehicle)))