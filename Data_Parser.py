import asyncio
import csv
import io
import re
import string

import aiofiles


async def match_cdk_to_actual_name(vehicle_name):
    async with aiofiles.open('WT-DATA.csv', mode='r', encoding='utf-8') as f:
        content = await f.read()
        
    # Use StringIO to allow csv.DictReader to work on the string content
    csv_file = io.StringIO(content)
    reader = csv.DictReader(csv_file)
    for row in reader:
        if row.get('wk_name') == vehicle_name.lower():
            alt_name = row.get('alt_name')
            return await normalize_name(alt_name) if alt_name else vehicle_name
    return vehicle_name

async def normalize_name(name: str) -> str:
    name = name.replace('_', ' ')
    allowed_punct = re.escape(string.punctuation)
    pattern = f'[^A-Za-z0-9{allowed_punct} ]'
    # Remove characters that don't match the allowed set
    normalized = re.sub(pattern, '', name)
    return normalized

#vehicle = "germ_pzkpfw_VI_ausf_h1_tiger_west"
#print(asyncio.run(match_cdk_to_actual_name(vehicle)))