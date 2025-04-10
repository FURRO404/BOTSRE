#Alarms.py
import json

import discord
from replit.object_storage import Client

from SQ_Info import fetch_squadron_info

client = Client()
# Function to take a snapshot of the members and their scores
async def take_snapshot(squadron_name):
    snapshot = await fetch_squadron_info(squadron_name)
    return snapshot

# Function to save the snapshot using Replit object storage
def save_snapshot(snapshot, guild_id, squadron_name, region=None):
    if region:
        key = f"SNAPSHOTS/{guild_id}-{squadron_name}-{region}-snapshot"
    else:
        key = f"SNAPSHOTS/{guild_id}-{squadron_name}-snapshot"
    client.upload_from_text(key, json.dumps(snapshot.to_dict()))
    print(f"Snapshot saved for {squadron_name} in guild {guild_id} under {region or 'default'} region")


# Function to load the snapshot using Replit object storage
def load_snapshot(guild_id, squadron_name, region=None):
    if region:
        key = f"SNAPSHOTS/{guild_id}-{squadron_name}-{region}-snapshot"
    else:
        key = f"SNAPSHOTS/{guild_id}-{squadron_name}-snapshot"
    try:
        snapshot_dict = json.loads(client.download_as_text(key))
        return discord.Embed.from_dict(snapshot_dict)
    except Exception as e:
        print(f"Error loading snapshot for {squadron_name} in guild {guild_id} under {region or 'default'} region: {e}")
        return None

#old_snapshot = {"fields": [{"inline": False, "name": "Total Members", "value": "128"}, {"inline": False, "name": "Total Points", "value": "46646"}, {"inline": False, "name": "\u00a0", "value": "Xnekron: 1905 points\nMarteX\u30c4: 1905 points\nFroziforst235: 1903 points\ndavid140601@psn: 1903 points\n\u041e\u0448\u0438\u0431\u043a\u0430\u30c5: 1902 points\nGround\\_2000: 1902 points\nnchk: 1902 points\nzizka1234: 1901 points\nEd\\_Grobovsky: 1901 points\nakkamme: 1901 points\nchikkleXD: 1901 points\nWaDDo\\_94: 1901 points\nZ\u043b\u043e\u0431\u0430: 1900 points\nxX\\_Bullpup\\_Xx: 1900 points\ndim\u0430s\\_f\u0435\u0435d1: 1892 points\nskyline\u5730\u5e73: 1888 points\nDemonOrque \u30c4: 1884 points\n\u041d\u0443\u0440\u0441\u0443\u043b\u0442\u0430\u043d: 1863 points\nDogfighterJimy: 1863 points\n\u0424\u0430\u043d\u0430\u0442 \u041e\u0448\u0438\u0431\u043a\u0438\u30c5: 1861 points\nsargas36: 1861 points\nKazooie\\_: 1856 points\nSyrupy\\_Pawjobz: 1854 points\nRaizyr: 1854 points\nDiz-Buster \u7389\u68d2\u30c4: 1852 points\nNITRO\\_Nord\\_: 1848 points\n\u0414\u0432\u043e\u0439\u043d\u043e\u0439 \u0430\u0433\u0435\u043d\u0442: 1847 points\nMellenium-\ud798: 1846 points\nNova\u30c4: 1843 points\n\u041f\u0438\u0440\u043e\u0436\u043e\u043a \u0422\u043e\u043a\u0441\u0438\u0447\u043d\u044b\u0439: 1835 points\ntersj9: 1830 points\nKichiRo \u4e37\u4eba\u4e37: 1829 points\n\u041a\u0430\u0437\u0430\u0445\u0441\u0442\u0430\u043d: 1829 points\n\u0415scA: 1828 points\nPessyJavczka: 1826 points\nGewehre: 1825 points\nKuraison: 1824 points\nFrovy: 1818 points\nShutlien: 1816 points\nDRUCE\\_WILLIS: 1814 points\n\u041b\u0430\u0434\u043do: 1811 points\nCHEHOV\\_A\\_P: 1805 points\n\u0427\u0430\u0439\\_: 1804 points"}, {"inline": False, "name": "\u00a0", "value": "N1kolaaa: 1803 points\n10 \u043a\u0412: 1799 points\nM\u0430slina: 1796 points\n\u0425\u043b\u0415\u0431\u0423\u0448\u0415\u043a: 1792 points\nWellFedCat: 1787 points\nUraazi: 1784 points\nIron Bl\u043eod: 1784 points\nTrIs0mYcUs: 1780 points\nJohnny Martinez: 1770 points\nRat\\_boyZ: 1766 points\n\\_YuLiKaTiBa\\_\\_: 1766 points\njostea: 1760 points\nNo\\_mercy\\_bomber: 1759 points\nNemcefil\\_t4: 1752 points\nSchido: 1746 points\nSpeed\\_\\_Fire\\_\\_: 1738 points\nCommaderClaux16: 1737 points\nGamB1t: 1737 points\nRaFFi\u30c4: 1734 points\nMrSquiddy: 1734 points\n\\_\u0421JI\u0443\u0433\u0430 3JI\u0430\\_: 1730 points\nLeft4\u0430ke: 1730 points\nMistrai: 1725 points\nFinally\\_Sound: 1723 points\n\\_JOKER\\_1998\\_: 1723 points\n\u043a\u0438\u043d\u043e: 1723 points\n\u0416\u0438\u0442\u0435\u043b\u044c\u0421\u0430\u043b\u043e\u0440\u0435\u0439\u0445\u0430: 1721 points\nRisenSunset: 1720 points\nBillytchi1213: 1719 points\nLAIT\\_2\\_VACHE: 1716 points\njte\\_rush\\_en\\_zoe@psn: 1713 points\nChocolamywaifu: 1711 points\nRozumnoGuzno: 1705 points\n\u041a\u0438\u0431\u043e\u0440\u0433\u0443\u0431\u0438\u0439\u0446\u0430: 1699 points\nSonne\\_99P: 1699 points\nWolfkrang\\_gaming@psn: 1697 points\ni1ng i1Hisoka\\_: 1696 points\n\u0424\u0430\u043d\u0430\u0442\u043a\u0430 LEET\u043e\u0432: 1694 points\nXxLukaxX: 1692 points\nKaspI: 1692 points"}, {"inline": False, "name": "\u00a0", "value": "\u041b\u0438\u0441\u0438\u0446\u0430 \u4e37\u4eba\u4e37: 1686 points\ncr4ban: 1676 points\nronmonster: 1673 points\nxX\\_\u041f\u0423\u0421\u042c\u041a\u0410\\_Xx: 1671 points\nBoosilhen: 1667 points\nSEBIGGA\u30b8: 1663 points\nSilenciO: 1658 points\nKKTWM: 1658 points\nhoke184: 1658 points\n\\_\\_C\\_B\\_A\\_T\\_\\_: 1654 points\n\\_Show\\_Master\\_: 1653 points\nvipy\\_11: 1648 points\n\\_Sizif\\_: 1638 points\n\u041c\u0430\u043c\u0430: 1636 points\niVACPOWER: 1633 points\nZ\u0430\u0442\u041eru G\u041ej\u041e: 1621 points\n\\_FixTime: 1613 points\nAnTech25: 1612 points\n1992 Space Movie: 1593 points\n\u0428\u0438\u0448\u0438\u0433\u0430: 1585 points\nALDI715: 1583 points\n\u0412\u0430\u043d\u044f\\_\u0411\u0443\u043b\u043f\u0430\u043f: 1569 points\n\u0423\u0412\u042b: 1567 points\nVodka\\_2: 1563 points\nStroke  3: 1554 points\nKrul Tepes: 1550 points\nDEADeye2460: 1548 points\n\\_KeGa\\_: 1540 points\nJebthebeast: 1539 points\nH\u0415NK: 1525 points\njte\\_rush\\_en\\_saxo: 1520 points\nLawi\\_\\_\\_19: 1507 points\nAN\\_AL\\_KARN\\_AVAL: 1476 points\n\u041b\u0451\u0445\u0430\\_New\\_Balance: 1413 points\nPapapagani88: 1389 points\njeanlo33: 1341 points\nHandFromCoffin: 1319 points\ndoodleZzz: 1246 points\n\\_Arctis\\_: 1204 points\nNeevix3451@live: 1006 points\nSlaimMaster#1: 784 points\nSchweinHotep: 412 points"}, {"inline": False, "name": "\u00a0", "value": "sanyashulgach: 411 points\n\u0416\u043c\u044b\u0445 airlines: 191 points\nflopper19: 0 points"}], "color": 65280, "type": "rich", "title": "Squadron Info: EXLY"}


#new_snapshot = {"fields": [{"inline": False, "name": "Total Members", "value": "128"}, {"inline": False, "name": "Total Points", "value": "46646"}, {"inline": False, "name": "\u00a0", "value": "Xnekron: 1905 points\nMarteX\u30c4: 1905 points\nFroziforst235: 1903 points\ndavid140601@psn: 1903 points\n\u041e\u0448\u0438\u0431\u043a\u0430\u30c5: 1902 points\nGround\\_2000: 1902 points\nnchk: 1902 points\nzizka1234: 1901 points\nEd\\_Grobovsky: 1901 points\nakkamme: 1901 points\nchikkleXD: 1901 points\nWaDDo\\_94: 1901 points\nZ\u043b\u043e\u0431\u0430: 1900 points\nxX\\_Bullpup\\_Xx: 1900 points\ndim\u0430s\\_f\u0435\u0435d1: 1892 points\nskyline\u5730\u5e73: 1888 points\nDemonOrque \u30c4: 1884 points\n\u041d\u0443\u0440\u0441\u0443\u043b\u0442\u0430\u043d: 1863 points\nDogfighterJimy: 1863 points\n\u0424\u0430\u043d\u0430\u0442 \u041e\u0448\u0438\u0431\u043a\u0438\u30c5: 1861 points\nsargas36: 1861 points\nKazooie\\_: 1856 points\nSyrupy\\_Pawjobz: 1854 points\nRaizyr: 1854 points\nDiz-Buster \u7389\u68d2\u30c4: 1852 points\nNITRO\\_Nord\\_: 1848 points\n\u0414\u0432\u043e\u0439\u043d\u043e\u0439 \u0430\u0433\u0435\u043d\u0442: 1847 points\nMellenium-\ud798: 1846 points\nNova\u30c4: 1843 points\n\u041f\u0438\u0440\u043e\u0436\u043e\u043a \u0422\u043e\u043a\u0441\u0438\u0447\u043d\u044b\u0439: 1835 points\ntersj9: 1830 points\nKichiRo \u4e37\u4eba\u4e37: 1829 points\n\u041a\u0430\u0437\u0430\u0445\u0441\u0442\u0430\u043d: 1829 points\n\u0415scA: 1828 points\nPessyJavczka: 1826 points\nGewehre: 1825 points\nKuraison: 1824 points\nFrovy: 1818 points\nShutlien: 1816 points\nDRUCE\\_WILLIS: 1814 points\n\u041b\u0430\u0434\u043do: 1811 points\nCHEHOV\\_A\\_P: 1805 points\n\u0427\u0430\u0439\\_: 1804 points"}, {"inline": False, "name": "\u00a0", "value": "N1kolaaa: 1803 points\n10 \u043a\u0412: 1799 points\nM\u0430slina: 1796 points\n\u0425\u043b\u0415\u0431\u0423\u0448\u0415\u043a: 1792 points\nWellFedCat: 1787 points\nUraazi: 1784 points\nIron Bl\u043eod: 1784 points\nTrIs0mYcUs: 1780 points\nJohnny Martinez: 1770 points\nRat\\_boyZ: 1766 points\n\\_YuLiKaTiBa\\_\\_: 1766 points\njostea: 1760 points\nNo\\_mercy\\_bomber: 1759 points\nNemcefil\\_t4: 1752 points\nSchido: 1746 points\nSpeed\\_\\_Fire\\_\\_: 1738 points\nCommaderClaux16: 1737 points\nGamB1t: 1737 points\nRaFFi\u30c4: 1734 points\nMrSquiddy: 1734 points\n\\_\u0421JI\u0443\u0433\u0430 3JI\u0430\\_: 1730 points\nLeft4\u0430ke: 1730 points\nMistrai: 1725 points\nFinally\\_Sound: 1723 points\n\\_JOKER\\_1998\\_: 1723 points\n\u043a\u0438\u043d\u043e: 1723 points\n\u0416\u0438\u0442\u0435\u043b\u044c\u0421\u0430\u043b\u043e\u0440\u0435\u0439\u0445\u0430: 1721 points\nRisenSunset: 1720 points\nBillytchi1213: 1719 points\nLAIT\\_2\\_VACHE: 1716 points\njte\\_rush\\_en\\_zoe@psn: 1713 points\nChocolamywaifu: 1711 points\nRozumnoGuzno: 1705 points\n\u041a\u0438\u0431\u043e\u0440\u0433\u0443\u0431\u0438\u0439\u0446\u0430: 1699 points\nSonne\\_99P: 1699 points\nWolfkrang\\_gaming@psn: 1697 points\ni1ng i1Hisoka\\_: 1696 points\n\u0424\u0430\u043d\u0430\u0442\u043a\u0430 LEET\u043e\u0432: 1694 points\nXxLukaxX: 1692 points\nKaspI: 1692 points"}, {"inline": False, "name": "\u00a0", "value": "\u041b\u0438\u0441\u0438\u0446\u0430 \u4e37\u4eba\u4e37: 1686 points\ncr4ban: 1676 points\nronmonster: 1673 points\nxX\\_\u041f\u0423\u0421\u042c\u041a\u0410\\_Xx: 1671 points\nBoosilhen: 1667 points\nSEBIGGA\u30b8: 1663 points\nSilenciO: 1658 points\nKKTWM: 1658 points\nhoke184: 1658 points\n\\_\\_C\\_B\\_A\\_T\\_\\_: 1654 points\n\\_Show\\_Master\\_: 1653 points\nvipy\\_11: 1648 points\n\\_Sizif\\_: 1638 points\n\u041c\u0430\u043c\u0430: 1636 points\niVACPOWER: 1633 points\nZ\u0430\u0442\u041eru G\u041ej\u041e: 1621 points\n\\_FixTime: 1613 points\nAnTech25: 1612 points\n1992 Space Movie: 1593 points\n\u0428\u0438\u0448\u0438\u0433\u0430: 1585 points\nALDI715: 1583 points\n\u0412\u0430\u043d\u044f\\_\u0411\u0443\u043b\u043f\u0430\u043f: 1569 points\n\u0423\u0412\u042b: 1567 points\nVodka\\_2: 1563 points\nStroke  3: 1554 points\nKrul Tepes: 1550 points\nDEADeye2460: 1548 points\n\\_KeGa\\_: 1540 points\nJebthebeast: 1539 points\nH\u0415NK: 1525 points\njte\\_rush\\_en\\_saxo: 1520 points\nLawi\\_\\_\\_19: 1507 points\nAN\\_AL\\_KARN\\_AVAL: 1476 points\n\u041b\u0451\u0445\u0430\\_New\\_Balance: 1413 points\nPapapagani88: 1389 points\njeanlo33: 1341 points\nHandFromCoffin: 1319 points\ndoodleZzz: 1246 points\n\\_Arctis\\_: 1204 points\nNeevix3451@live: 1006 points\nSlaimMaster#1: 784 points\nSchweinHotep: 412 points"}, {"inline": False, "name": "\u00a0", "value": "sanyashulgach: 411 points\n\u0416\u043c\u044b\u0445 airlines: 191 points\nflopper19: 0 points"}], "color": 65280, "type": "rich", "title": "Squadron Info: EXLY"}


def compare_snapshots(old_snapshot, new_snapshot):
    old_members = {}
    new_members = {}
    old_total_members = 0
    new_total_members = 0

    for field in old_snapshot.fields:
        if field.name == "Total Members":
            try:
                old_total_members = int(field.value)
            except ValueError as e:
                print(f"Error parsing old members: {field.value}, error: {e}")

    for field in new_snapshot.fields:
        if field.name == "Total Members":
            try:
                new_total_members = int(field.value)
            except ValueError as e:
                print(f"Error parsing new members: {field.value}, error: {e}")
    
    # Extract old members
    for field in old_snapshot.fields:
        if field.name == "\u00a0":
            values = field.value.split("\n")
            for value in values:
                try:
                    member_name = value.split(": ")[0].replace('\\_', '_')
                    points = int(value.split(": ")[1].split()[0])
                    old_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing old snapshot field: {value}, error: {e}")

    # Extract new members
    for field in new_snapshot.fields:
        if field.name == "\u00a0":
            values = field.value.split("\n")
            for value in values:
                try:
                    member_name = value.split(": ")[0].replace('\\_', '_')
                    points = int(value.split(": ")[1].split()[0])
                    new_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing new snapshot field: {value}, error: {e}")

    
    if not new_members:
        return {}, {}


    left_members = {}
    name_changes = {}

    # Create a reverse lookup for new members' points -> name
    points_to_name = {points: name for name, points in new_members.items()}

    for member, points in old_members.items():
        if member not in new_members:
            if points not in points_to_name:    
                left_members[member] = points
            else:
                new_name = points_to_name[points]  # Get the new name based on matching points
                name_changes[member] = (new_name)  # Store old name -> new name

    return left_members, name_changes


def compare_snapshot_dict(old_snapshot: dict, new_snapshot: dict):
    old_members = {}
    new_members = {}
    old_total_members = 0
    new_total_members = 0

    # Extract total members
    for field in old_snapshot.get("fields", []):
        if field.get("name") == "Total Members":
            try:
                old_total_members = int(field.get("value", 0))
            except ValueError as e:
                print(f"Error parsing old members: {field.get('value')}, error: {e}")

    for field in new_snapshot.get("fields", []):
        if field.get("name") == "Total Members":
            try:
                new_total_members = int(field.get("value", 0))
            except ValueError as e:
                print(f"Error parsing new members: {field.get('value')}, error: {e}")

    # Extract old members
    for field in old_snapshot.get("fields", []):
        if field.get("name") == "\u00a0":
            values = field.get("value", "").split("\n")
            for value in values:
                try:
                    member_name, points = value.split(": ")
                    member_name = member_name.replace('\\_', '_')
                    points = int(points.split()[0])
                    old_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing old snapshot field: {value}, error: {e}")

    # Extract new members
    for field in new_snapshot.get("fields", []):
        if field.get("name") == "\u00a0":
            values = field.get("value", "").split("\n")
            for value in values:
                try:
                    member_name, points = value.split(": ")
                    member_name = member_name.replace('\\_', '_')
                    points = int(points.split()[0])
                    new_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing new snapshot field: {value}, error: {e}")

    if not new_members:
        return {}, {}

    left_members = {}
    name_changes = {}

    # Create a reverse lookup for new members' points -> name
    points_to_name = {points: name for name, points in new_members.items()}

    for member, points in old_members.items():
        if member not in new_members:
            if points not in points_to_name:    
                left_members[member] = points
            else:
                new_name = points_to_name[points]  # Get the new name based on matching points
                name_changes[member] = (new_name, points)  # Store old name -> new name with points

    return left_members



def compare_points(old_snapshot, new_snapshot):
    old_members = {}
    new_members = {}
    old_total_points = 0

    # Extract old total points & members' points
    for field in old_snapshot.fields:
        if field.name == "Total Points":
            try:
                old_total_points = int(field.value)
            except ValueError as e:
                print(f"Error parsing total points: {field.value}, error: {e}")

        if field.name == "\u00a0":  # Member points data
            values = field.value.split("\n")
            for value in values:
                try:
                    member_name = value.split(": ")[0].replace('\\_', '_')
                    points = int(value.split(": ")[1].split()[0])
                    old_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing old snapshot field: {value}, error: {e}")

    # Extract new members' points
    for field in new_snapshot.fields:
        if field.name == "\u00a0":
            values = field.value.split("\n")
            for value in values:
                try:
                    member_name = value.split(": ")[0].replace('\\_', '_')
                    points = int(value.split(": ")[1].split()[0])
                    new_members[member_name] = points
                except (IndexError, ValueError) as e:
                    print(f"Error parsing new snapshot field: {value}, error: {e}")

    # Compare old and new points to detect changes
    points_changes = {}

    # Check existing members
    for member, old_points in old_members.items():
        new_points = new_members.get(member, 0)  # If player left, set their points to zero
        if new_points != old_points:
            points_changes[member] = (new_points - old_points, new_points)

    # Check new members not in old_members
    for member, new_points in new_members.items():
        if member not in old_members:  # New player
            if new_points != 0: #Only include them if they made points
                points_changes[member] = (new_points, new_points)

    return points_changes, old_total_points


def compare_points_dict(old_snapshot, new_snapshot):
    old_members = {}
    new_members = {}
    old_total_points = 0  # Store old total points

    def extract_members(snapshot):
        members = {}
        total_points = 0

        for field in snapshot.get("fields", []):  # Access fields as a list
            if field["name"] == "Total Points":
                try:
                    total_points = int(field["value"])
                except ValueError as e:
                    print(f"Error parsing total points: {field['value']}, error: {e}")

            if field["name"] == "\u00a0":  # Member points data
                values = field["value"].strip().split("\n")
                for value in values:
                    try:
                        parts = value.rsplit(": ", 1)  # Reverse split to avoid issues with ":" in names
                        if len(parts) == 2:
                            member_name = parts[0].strip().replace('\\_', '_')  # Trim spaces
                            points = int(parts[1].split()[0])  # Extract only the numeric part
                            members[member_name] = points
                        else:
                            print(f"Skipping invalid entry: {repr(value)}")
                    except (IndexError, ValueError) as e:
                        print(f"Error parsing snapshot field: {value}, error: {e}")

        return total_points, members

    # Extract members and total points
    old_total_points, old_members = extract_members(old_snapshot)
    _, new_members = extract_members(new_snapshot)

    # Compare old and new points to detect changes
    points_changes = {}

    # Check existing members
    for member, old_points in old_members.items():
        new_points = new_members.get(member, 0)  # If player left, set their points to zero
        if new_points != old_points:
            points_changes[member] = (new_points - old_points, new_points)

    # Check new members not in old_members
    for member, new_points in new_members.items():
        if member not in old_members:  # New player
            if new_points != 0: #Only include them if they made points
                points_changes[member] = (new_points, new_points)

    return points_changes, old_total_points

#meow, purr = compare_snapshot_dict(old_snapshot, new_snapshot) 
#print(f"Meow: {meow}")
#print(f"Purr: {purr}")