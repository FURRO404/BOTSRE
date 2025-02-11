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
        key = f"{guild_id}-{squadron_name}-{region}-snapshot"
    else:
        key = f"{guild_id}-{squadron_name}-snapshot"
    client.upload_from_text(key, json.dumps(snapshot.to_dict()))
    print(f"Snapshot saved for {squadron_name} in guild {guild_id} under {region or 'default'} region")


# Function to load the snapshot using Replit object storage
def load_snapshot(guild_id, squadron_name, region=None):
    if region:
        key = f"{guild_id}-{squadron_name}-{region}-snapshot"
    else:
        key = f"{guild_id}-{squadron_name}-snapshot"
    try:
        snapshot_dict = json.loads(client.download_as_text(key))
        return discord.Embed.from_dict(snapshot_dict)
    except Exception as e:
        print(f"Error loading snapshot for {squadron_name} in guild {guild_id} under {region or 'default'} region: {e}")
        return None


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
        return "EMPTY"

    left_members = {}
    if new_total_members < old_total_members:
        for member, points in old_members.items():
            if member not in new_members and points > 0:
                left_members[member] = points
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
    for member, old_points in old_members.items():
        if member in new_members:
            new_points = new_members[member]
            if new_points != old_points:
                points_changes[member] = (new_points - old_points, new_points)  

    return points_changes, old_total_points


#old_snapshot = {"fields": [{"inline": false, "name": "Total Members", "value": "127"}, {"inline": false, "name": "Total Points", "value": "45831"}, {"inline": false, "name": "\u00a0", "value": "Xnekron: 1905 points\nMarteX\u30c4: 1905 points\nFroziforst235: 1903 points\n\u041e\u0448\u0438\u0431\u043a\u0430\u30c5: 1902 points\nAir\\_2000: 1902 points\nzizka1234: 1901 points\nEd\\_Grobovsky: 1901 points\nZ\u043b\u043e\u0431\u0430: 1900 points\nxX\\_Bullpup\\_Xx: 1900 points\ndavid140601@psn: 1865 points\nDemonOrque \u30c4: 1863 points\nsargas36: 1861 points\nnchk: 1855 points\nDiz-Buster \u7389\u68d2\u30c4: 1852 points\n\u041d\u0443\u0440\u0441\u0443\u043b\u0442\u0430\u043d: 1851 points\nNITRO\\_Nord\\_: 1848 points\nMellenium-\ud798: 1846 points\n\u0414\u0432\u043e\u0439\u043d\u043e\u0439 \u0430\u0433\u0435\u043d\u0442: 1840 points\n\u0424\u0430\u043d\u0430\u0442 \u041e\u0448\u0438\u0431\u043a\u0438\u30c5: 1838 points\nIron Bl\u043eod: 1836 points\nRisenSunset: 1830 points\ntersj9: 1830 points\nKichiRo \u4e37\u4eba\u4e37: 1829 points\nchikkleXD: 1826 points\nGewehre: 1825 points\nKuraison: 1824 points\n\u041a\u0430\u0437\u0430\u0445\u0441\u0442\u0430\u043d: 1823 points\n\u041b\u0430\u0434\u043do: 1821 points\nDRUCE\\_WILLIS: 1814 points\nFrovy: 1806 points\nNova\u30c4: 1806 points\nCHEHOV\\_A\\_P: 1805 points\nKazooie\\_: 1803 points\nM\u0430slina: 1800 points\nronmonster: 1781 points\nTrIs0mYcUs: 1780 points\nShutlien: 1779 points\nRaizyr: 1776 points\nNotSoToothless\\_: 1763 points\nC\u0415M\u0415N\\_B\u0410KIN: 1762 points\nNo\\_mercy\\_bomber: 1759 points\nNemcefil\\_t4: 1752 points"}, {"inline": false, "name": "\u00a0", "value": "\u0425\u043b\u0415\u0431\u0423\u0448\u0415\u043a: 1745 points\njostea: 1741 points\n\\_YuLiKaTiBa\\_\\_: 1739 points\nskyline\u5730\u5e73: 1738 points\n\u0427\u0430\u0439\\_: 1737 points\nRaFFi\u30c4: 1734 points\nMrSquiddy: 1734 points\nakkamme: 1732 points\nBillytchi1213: 1730 points\n\\_JOKER\\_1998\\_: 1728 points\nRat\\_boyZ: 1728 points\ni1ng i1Hisoka\\_: 1727 points\nMistrai: 1725 points\nGamB1t: 1720 points\n\u0424\u0430\u043d\u0430\u0442\u043a\u0430 LEET\u043e\u0432: 1715 points\njte\\_rush\\_en\\_zoe@psn: 1713 points\nChocolamywaifu: 1711 points\nXxLukaxX: 1709 points\nN1kolaaa: 1709 points\nSchido: 1705 points\n\u0415scA: 1704 points\nPessyJavczka: 1703 points\n10 \u043a\u0412: 1700 points\n\\_Sizif\\_: 1699 points\n\u041a\u0438\u0431\u043e\u0440\u0433\u0443\u0431\u0438\u0439\u0446\u0430: 1699 points\nSonne\\_99P: 1699 points\nWolfkrang\\_gaming@psn: 1697 points\nCommaderClaux16: 1692 points\nKaspI: 1692 points\nUraazi: 1688 points\nWellFedCat: 1682 points\nvipy\\_11: 1681 points\nJohnny Martinez: 1681 points\nSilenciO: 1673 points\nSpeed\\_\\_Fire\\_\\_: 1670 points\n\u041f\u0438\u0440\u043e\u0436\u043e\u043a \u0422\u043e\u043a\u0441\u0438\u0447\u043d\u044b\u0439: 1662 points\nKrul Tepes: 1661 points\n\\_\\_C\\_B\\_A\\_T\\_\\_: 1661 points\nSEBIGGA\u30b8: 1659 points\n\\_Show\\_Master\\_: 1653 points\nLeft4\u0430ke: 1639 points"}, {"inline": false, "name": "\u00a0", "value": "\\_\u0421JI\u0443\u0433\u0430 3JI\u0430\\_: 1638 points\nLAIT\\_2\\_VACHE: 1637 points\n\u041c\u0430\u043c\u0430: 1636 points\nm\u0430kSS: 1632 points\nZ\u0430\u0442\u041eru G\u041ej\u041e: 1621 points\nFinally\\_Sound: 1613 points\nAnTech25: 1612 points\ncr4ban: 1603 points\nxX\\_\u041f\u0423\u0421\u042c\u041a\u0410\\_Xx: 1601 points\nALDI715: 1598 points\nKKTWM: 1598 points\n\u0412\u0430\u043d\u044f\\_\u0411\u0443\u043b\u043f\u0430\u043f: 1574 points\n1992 Space Movie: 1570 points\n\u0423\u0412\u042b: 1567 points\nVigilant\\_: 1563 points\n\\_FixTime: 1551 points\nhoke184: 1547 points\nRozumnoGuzno: 1540 points\n\\_KeGa\\_: 1540 points\nJebthebeast: 1539 points\nH\u0415NK: 1525 points\nBrique 1-2: 1520 points\nBoosilhen: 1512 points\niVACPOWER: 1512 points\nDogfighterJimy: 1490 points\n\u043a\u0438\u043d\u043e: 1468 points\nAN\\_AL\\_KARN\\_AVAL: 1436 points\nLawi\\_\\_\\_19: 1428 points\nStroke  3: 1355 points\nPapapagani88: 1343 points\nHandFromCoffin: 1319 points\n\\_Arctis\\_: 1204 points\njeanlo33: 1038 points\nNeevix3451@live: 1006 points\nDEADeye2460: 969 points\n\u041b\u0451\u0445\u0430\\_New\\_Balance: 882 points\ndoodleZzz: 878 points\nPaPoPaPla: 863 points\nSlaimMaster#1: 784 points\nkuhnilingus: 502 points\nConqueror208: 413 points\nLe Killback@live: 403 points"}, {"inline": false, "name": "\u00a0", "value": "\u0416\u043c\u044b\u0445 airlines: 191 points\nXantum: 0 points"}], "color": 65280, "type": "rich", "title": "Squadron Info: EXLY"}


#new_snapshot = {'fields': [{'inline': False, 'name': 'Total Members', 'value': '128'}, {'inline': False, 'name': 'Total Points', 'value': '45831'}, {'inline': False, 'name': '\xa0', 'value': 'Xnekron: 1905 points\nMarteXツ: 1905 points\nFroziforst235: 1903 points\nОшибкаヅ: 1902 points\nGround\\_2000: 1902 points\nzizka1234: 1901 points\nEd\\_Grobovsky: 1901 points\nZлоба: 1900 points\nxX\\_Bullpup\\_Xx: 1900 points\ndavid140601@psn: 1865 points\nDemonOrque ツ: 1863 points\nsargas36: 1861 points\nnchk: 1855 points\nDiz-Buster 玉棒ツ: 1852 points\nНурсултан: 1851 points\nNITRO\\_Nord\\_: 1848 points\nMellenium-힘: 1846 points\nДвойной агент: 1840 points\nФанат Ошибкиヅ: 1838 points\nIron Blоod: 1836 points\nRisenSunset: 1830 points\ntersj9: 1830 points\nKichiRo 丷人丷: 1829 points\nchikkleXD: 1870 points\nGewehre: 1825 points\nKuraison: 1824 points\nКазахстан: 1823 points\nЛаднo: 1821 points\nDRUCE\\_WILLIS: 1814 points\nNovaツ: 1806 points\nCHEHOV\\_A\\_P: 1805 points\nKazooie\\_: 1803 points\nronmonster: 1781 points\nTrIs0mYcUs: 1780 points\nShutlien: 1779 points\nRaizyr: 1776 points\nNotSoToothless\\_: 1763 points\nNo\\_mercy\\_bomber: 1759 points\nNemcefil\\_t4: 1752 points\nХлЕбУшЕк: 1745 points\n\\_YuLiKaTiBa\\_\\_: 1739 points\nskyline地平: 1738 points'}, {'inline': False, 'name': '\xa0', 'value': 'Чай\\_: 1737 points\nRaFFiツ: 1734 points\nMrSquiddy: 1734 points\nakkamme: 1732 points\ni1ng i1Hisoka\\_: 1727 points\nMistrai: 1725 points\n\\_JOKER\\_1998\\_: 1723 points\njte\\_rush\\_en\\_zoe@psn: 1713 points\nChocolamywaifu: 1711 points\nXxLukaxX: 1709 points\nN1kolaaa: 1709 points\nFrovy: 1706 points\nSchido: 1705 points\nЕscA: 1704 points\nRat\\_boyZ: 1703 points\nPessyJavczka: 1703 points\n10 кВ: 1700 points\nКиборгубийца: 1699 points\nSonne\\_99P: 1699 points\nWolfkrang\\_gaming@psn: 1697 points\njostea: 1695 points\nCommaderClaux16: 1692 points\nKaspI: 1692 points\nUraazi: 1688 points\nMаslina: 1685 points\nWellFedCat: 1682 points\nvipy\\_11: 1681 points\nSilenciO: 1673 points\nSpeed\\_\\_Fire\\_\\_: 1666 points\nGamB1t: 1664 points\nПирожок Токсичный: 1662 points\nKrul Tepes: 1661 points\nSEBIGGAジ: 1659 points\nФанатка LEETов: 1659 points\nJohnny Martinez: 1656 points\n\\_СJIуга 3JIа\\_: 1654 points\nLeft4аke: 1654 points\n\\_Show\\_Master\\_: 1653 points\nCЕMЕN\\_BАKIN: 1648 points\nFinally\\_Sound: 1644 points\n\\_Sizif\\_: 1637 points'}, {'inline': False, 'name': '\xa0', 'value': 'LAIT\\_2\\_VACHE: 1637 points\nМама: 1636 points\n\\_\\_C\\_B\\_A\\_T\\_\\_: 1634 points\nZатОru GОjО: 1621 points\nRozumnoGuzno: 1619 points\nBillytchi1213: 1617 points\ncr4ban: 1614 points\nAnTech25: 1612 points\nxX\\_ПУСЬКА\\_Xx: 1599 points\nKKTWM: 1598 points\nmаkSS: 1580 points\nALDI715: 1571 points\n1992 Space Movie: 1570 points\nВаня\\_Булпап: 1569 points\nУВЫ: 1567 points\nVigilant\\_: 1563 points\n\\_FixTime: 1559 points\nhoke184: 1552 points\n\\_KeGa\\_: 1540 points\nJebthebeast: 1539 points\nHЕNK: 1525 points\nBrique 1-2: 1520 points\nBoosilhen: 1512 points\niVACPOWER: 1512 points\nDogfighterJimy: 1490 points\nAN\\_AL\\_KARN\\_AVAL: 1475 points\nкино: 1468 points\nLawi\\_\\_\\_19: 1428 points\nStroke  3: 1355 points\nPapapagani88: 1343 points\nHandFromCoffin: 1319 points\nЛисица 丷人丷: 1230 points\n\\_Arctis\\_: 1204 points\nЛёха\\_New\\_Balance: 1195 points\njeanlo33: 1038 points\nNeevix3451@live: 1006 points\nDEADeye2460: 969 points\ndoodleZzz: 878 points\nPaPoPaPla: 863 points\nSlaimMaster#1: 784 points\nWaDDo\\_94: 441 points\nConqueror208: 413 points'}, {'inline': False, 'name': '\xa0', 'value': 'Шишига: 408 points\nЖмых airlines: 191 points\nXantum: 0 points'}], 'color': 65280, 'type': 'rich', 'title': 'Squadron Info: EXLY'}



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
    for member, old_points in old_members.items():
        if member in new_members:
            new_points = new_members[member]
            if new_points != old_points:
                points_changes[member] = (new_points - old_points, new_points)

    return points_changes, old_total_points

#meow, purr = compare_points_dict(old_snapshot, new_snapshot) 
#print(f"Meow: {meow}")
#print(f"Purr: {purr}")