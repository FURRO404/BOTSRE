import csv
import io
import aiofiles

async def match_cdk_to_actual_name(vehicle_name):
    async with aiofiles.open('WT-DATA.csv', mode='r', encoding='utf-8') as f:
        content = await f.read()
        
    # Use StringIO to allow csv.DictReader to work on the string content
    csv_file = io.StringIO(content)
    reader = csv.DictReader(csv_file)
    for row in reader:
        if row.get('wk_name') == vehicle_name.lower():
            return row.get('alt_name')
    return vehicle_name

#import asyncio
#vehicle = "germ_pzkpfw_VI_ausf_h1_tiger"
#alt_name = asyncio.run(match_cdk_to_actual_name(vehicle))
#print(alt_name)