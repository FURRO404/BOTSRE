import asyncio
import re
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from Data_Parser import get_dict_from_list


async def create_scoreboard(match_details, winning_team, team1_details, team2_details, map_file, output_path):
    """
    Creates a full-screen scoreboard with very large text, covering the entire image.
    Column headers for the stat columns are replaced by icons based on a custom mapping.
    The team name now appears only in the table header (first column), drawn with a larger
    font, and if that team is the winner, it is rendered in a golden color.
    """

    # --- Load Background ---
    map_file = re.sub(r"^\s*\[[^]]+\]\s*", "", map_file)
    map_name = map_file
    map_file = map_file.replace(" ", "_")
    map_image_path = f"MAPS/{map_file}.jpg"
    background = Image.open(map_image_path).convert("RGBA")
    bg_width, bg_height = background.size

    # Create overlay covering the entire image
    overlay = Image.new("RGBA", (bg_width, bg_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    margin = 30
    draw.rectangle([margin, margin, bg_width - margin, bg_height - margin], fill=(0, 0, 0, 150))

    # Font sizes and paths
    TITLE_FONT_SIZE = int(bg_width * 0.03)
    TEAM_FONT_SIZE  = int(bg_width * 0.03)
    BODY_FONT_SIZE  = int(bg_width * 0.019)
    STAT_FONT_SIZE  = int(bg_width * 0.022)
    COMP_FONT_SIZE = int(bg_width * 0.018)
    

    font_path = "fonts/arial_unicode_ms.otf"
    font_title = ImageFont.truetype(font_path, TITLE_FONT_SIZE)
    font_team  = ImageFont.truetype(font_path, TEAM_FONT_SIZE)
    font_body  = ImageFont.truetype(font_path, BODY_FONT_SIZE)
    stat_font  = ImageFont.truetype(font_path, STAT_FONT_SIZE)
    comp_font  = ImageFont.truetype(font_path, COMP_FONT_SIZE)

    resample_filter = Image.Resampling.LANCZOS

    # --- Draw match_details (human-readable) in small text, top-right ---
    INFO_FONT_SIZE = int(bg_width * 0.015)
    info_font      = ImageFont.truetype(font_path, INFO_FONT_SIZE)
    padding        = 15

    # convert epoch to human-readable UTC
    ts_epoch = int(match_details['utc_timestamp'])
    dt_utc   = datetime.utcfromtimestamp(ts_epoch)
    ts_text  = dt_utc.strftime("%H:%M:%S - %Y-%m-%d UTC")
    sid_text = f"{match_details['session_id']}"

    # position timestamp
    ts_bbox = draw.textbbox((0,0), ts_text, font=info_font)
    x_ts    = bg_width - margin - (ts_bbox[2]-ts_bbox[0]) - padding
    y_ts    = margin + padding
    draw.text((x_ts, y_ts), ts_text, font=info_font, fill=(200,200,200,255))

    # position session ID below it
    sid_bbox = draw.textbbox((0,0), sid_text, font=info_font)
    x_sid    = bg_width - margin - (sid_bbox[2]-sid_bbox[0]) - padding
    line_spacing = 15   # ← play with this number
    y_sid = y_ts + (ts_bbox[3] - ts_bbox[1]) + line_spacing
    draw.text((x_sid, y_sid), sid_text, font=info_font, fill=(200,200,200,255))

    
    # --- Draw Top Titles (centered) ---
    title_text = f"{map_name}"
    win_text   = f"Winner - {winning_team}"

    # Starting vertical position
    y = 50

    # Draw centered map name
    title_bbox  = draw.textbbox((0, 0), title_text, font=font_title)
    title_width = title_bbox[2] - title_bbox[0]
    x_center    = (bg_width - title_width) // 2
    draw.text((x_center, y), title_text, font=font_title, fill=(255, 255, 255, 255))
    title_height = title_bbox[3] - title_bbox[1]
    y += title_height + 40

    # Draw centered winner text
    win_bbox   = draw.textbbox((0, 0), win_text, font=font_title)
    win_width  = win_bbox[2] - win_bbox[0]
    x_center   = (bg_width - win_width) // 2
    draw.text((x_center, y), win_text, font=font_title, fill=(255, 215, 0, 255))
    win_height = win_bbox[3] - win_bbox[1]
    y_start    = y + win_height + 60

    # Calculate layout for the two team columns
    x_start     = margin * 3
    gap_between = 40
    col_width   = (bg_width - (x_start * 2) - gap_between) // 2


    def draw_team(team_data, start_x, start_y, section_width):
        # Get team name (squadron) and set starting y_offset.
        squadron = team_data.get("squadron", "Unknown")
        y_offset = start_y

        # Convert vehicles to comp notation
        vehicle_list = [player["vehicle"] for player in team_data["players"]]
        notation_list = get_dict_from_list(vehicle_list)
        #Notation example: {'F': 3, 'T': 3, 'AA': 1, 'B': 1}

        # In this order: Fighters, Bombers, Helicopters, Tanks, AA
        # --- Draw comp notation next to squadron header ---
        comp_order = [("F", "Fighters"), ("B", "Bombers"), ("H", "Helicopters"), ("T", "Tanks"), ("AA", "AA")]
        # measure the width of the squadron text so we know where to start
        squad_bbox   = draw.textbbox((0, 0), squadron, font=font_team)
        squad_width  = squad_bbox[2] - squad_bbox[0]
        # x,y to drop our little comp tags
        comp_x       = start_x + squad_width + 20
        
        COMP_Y_SHIFT   = 8
        comp_y = y_offset + (font_team.size - COMP_FONT_SIZE) // 2
        comp_y += COMP_Y_SHIFT

        for code, _ in comp_order:
            cnt = notation_list.get(code, 0)
            if cnt > 0:
                txt = f"{code}{cnt}"
                draw.text((comp_x, comp_y), txt, font=comp_font, fill=(255,255,255,255))
                width = draw.textbbox((0,0), txt, font=comp_font)[2]
                comp_x += width + 15

        
        
        # Define columns with the first column showing the team name.
        columns = [squadron, "Air", "Ground", "Assists", "Deaths", "Caps"]
        num_cols = len(columns)
        num_stat_cols = num_cols - 1
    
        # Reserve a stat area on the right of the section.
        stat_area_width = int(section_width * 0.425)
        stat_start = start_x + section_width - stat_area_width
    
        # For column 0 use start_x; for stat columns, distribute evenly.
        col_positions = [start_x]
        for i in range(num_stat_cols):
            col_x = stat_start + int(i * stat_area_width / num_stat_cols)
            col_positions.append(col_x)
    
        # ----- Draw Column Headers (with icons for stat columns) -----
        icon_mapping = {
            "Air": "ICONS/fighter_icon.png",
            "Ground": "ICONS/tank_icon.png",
            "Assists": "ICONS/assists_icon.png",
            "Deaths": "ICONS/deaths_icon.png",
            "Caps": "ICONS/cap_icon.png"
        }
        icon_size = int(STAT_FONT_SIZE * 1.5)
    
        for i, col_name in enumerate(columns):
            icon_file = icon_mapping.get(col_name)
            if icon_file:
                try:
                    icon_img = Image.open(icon_file).convert("RGBA")
                    icon_img = icon_img.resize((icon_size, icon_size), resample_filter)
                    icon_shift = 20  # shift icons to the left
                    icon_y_offset = 20  # shift icons down
                    overlay.paste(icon_img, (col_positions[i] - icon_shift, y_offset + icon_y_offset), icon_img)
                except Exception as e:
                    print(e)
                    draw.text((col_positions[i], y_offset), col_name, font=stat_font, fill=(200, 200, 200, 255))
            else:
                # For the first column (team name), use a larger font and golden if winner.
                if i == 0:
                    team_color = (255, 215, 0, 255) if squadron == winning_team else (255, 255, 255, 255)
                    draw.text((col_positions[i], y_offset), col_name, font=font_team, fill=team_color)
                else:
                    draw.text((col_positions[i], y_offset), col_name, font=stat_font, fill=(200, 200, 200, 255))
        row_height = icon_size + 10
        y_offset += row_height + 20
    
        # --- Sort players by score in descending order ---
        players_sorted = sorted(team_data.get("players", []), key=lambda player: int(player.get("score", 0)), reverse=True)
    
        Username_fill = (250, 227, 200, 255)
        Living_vehicle_fill = (255, 255, 255, 255)
        Dead_vehicle_fill = (200, 200, 200, 255)
    
        # Draw each player's row, adding the vehicle icon to the left of their text.
        for player in players_sorted:
            player_name = player.get("nick", "")
            player_name = player_name.replace("@live", "")
            player_name = player_name.replace("@psn", "")
            
            player_vehicle = player.get("vehicle_new", "")
            player_vehicle = player_vehicle.replace("Weizman's ", "")
            player_vehicle = player_vehicle.replace("Plagis' ", "")

            
            vehicle_img_name = player.get("vehicle", "")
            vehicle_icon_img = None
            vehicle_icon_size = int(BODY_FONT_SIZE * 2.35)
            
            if vehicle_img_name:
                vehicle_icon_path = f"ICONS/{vehicle_img_name.lower()}.png"
                try:
                    vehicle_icon_img = Image.open(vehicle_icon_path).convert("RGBA")
                    vehicle_icon_img = vehicle_icon_img.resize((vehicle_icon_size, vehicle_icon_size), resample_filter)
                except FileNotFoundError:
                    # Leave vehicle_icon_img as None if the file isn't found.
                    vehicle_icon_img = None
    
            # Compute bounding boxes for the texts
            name_bbox = draw.textbbox((0, 0), player_name, font=font_body)
            name_height = name_bbox[3] - name_bbox[1]
            vehicle_bbox = draw.textbbox((0, 0), player_vehicle, font=font_body)
            vehicle_height = vehicle_bbox[3] - vehicle_bbox[1]
            identity_height = name_height + 5 + vehicle_height
    
            # Determine row height from the text block and the icon
            row_height = max(identity_height, vehicle_icon_size)
    
            # Vertical offsets to center both the icon and text within the row.
            text_y = y_offset + (row_height - identity_height) // 2
            icon_y = y_offset + (row_height - vehicle_icon_size) // 2
    
            gap_between_icon_and_text = 5
            # Place icon at the beginning of the first column (col_positions[0])
            icon_x = col_positions[0]
            # Shift text to the right by the width of the icon plus a gap.
            text_x = col_positions[0] + vehicle_icon_size + gap_between_icon_and_text
    
            # Paste the vehicle icon if it is loaded successfully.
            if vehicle_icon_img is not None:
                overlay.paste(vehicle_icon_img, (icon_x - 15, icon_y + 15), vehicle_icon_img)
    
            # Draw the player's name and vehicle text.
            draw.text((text_x, text_y), player_name, font=font_body, fill=Username_fill)
            
            if int(player.get("deaths", 0)) > 0:
                draw.text((text_x, text_y + name_height + 10), player_vehicle, font=font_body, fill=Dead_vehicle_fill)
            else:
                draw.text((text_x, text_y + name_height + 10), player_vehicle, font=font_body, fill=Living_vehicle_fill)
    
            # Stat values for columns: Air, Ground, Assists, Deaths, Caps
            stat_values = [
                int(player.get("air_kills", 0)),
                int(player.get("ground_kills", 0)),
                int(player.get("assists", 0)),
                int(player.get("deaths", 0)),
                int(player.get("captures", 0)),
            ]
            stat_bbox   = draw.textbbox((0, 0), "0", font=stat_font)
            stat_height = stat_bbox[3] - stat_bbox[1]

            # Column names in the same order as stat_values
            stat_names = ["Air", "Ground", "Assists", "Deaths", "Caps"]

            for name, num, x in zip(stat_names, stat_values, col_positions[1:]):
                if name in ("Air", "Ground") and num > 0:
                    fill = (0, 255, 0, 255)          # green
                elif name == "Deaths" and num > 0:
                    fill = (255, 0, 0, 255)          # red
                elif name == "Caps" and num > 0:
                    fill = (255, 255, 0, 255)        # gold
                elif name == "Assists" and num > 0:
                    fill = (80, 120, 245, 255)
                else:
                    fill = (255, 255, 255, 255)      # white

                draw.text(
                    (x, y_offset + (row_height - stat_height) // 2),
                    str(num),
                    font=stat_font,
                    fill=fill
                )
            y_offset += row_height + 10
    
    # Draw Team 1 (left column)
    draw_team(team1_details, x_start, y_start, col_width)
    # Draw Team 2 (right column)
    draw_team(team2_details, x_start + col_width + gap_between, y_start, col_width)
    
    # Merge overlay onto background and save
    final_img = Image.alpha_composite(background, overlay)
    final_img.save(output_path)
    



# Example usage:
async def test():
    team1 = {
        "squadron": "9615",
        "players": [
            {
                "uid": 145639262,
                "nick": "bullpuppy\u30c5",
                "index": 0,
                "vehicle": "spitfire_ix",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 1,
                "captures": 0,
                "score": 71
            },
            {
                "uid": 37276368,
                "nick": "\u044f\u0434\u0435\u0440\u043d\u044b\u0439 \u043f\u0438\u0432\u0430\u0441",
                "index": 7,
                "vehicle": "jp_m4a3e8_76w_sherman",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 1,
                "deaths": 1,
                "captures": 0,
                "score": 100
            },
            {
                "uid": 44230049,
                "nick": "doodleZzz",
                "index": 9,
                "vehicle": "spitfire_ix_usa",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 1,
                "captures": 0,
                "score": 93
            },
            {
                "uid": 48597348,
                "nick": "skyline\u5730\u5e73",
                "index": 10,
                "vehicle": "jp_m4a3e8_76w_sherman",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 1,
                "captures": 0,
                "score": 70
            },
            {
                "uid": 60278485,
                "nick": "Diablo_Kraike",
                "index": 11,
                "vehicle": "jp_m4a3e8_76w_sherman",
                "vehicle_new": "meow",
                "air_kills": 1,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 1,
                "captures": 0,
                "score": 520
            },
            {
                "uid": 68148324,
                "nick": "SchweinHotep",
                "index": 12,
                "vehicle": "tu-2_postwar_late",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 1,
                "captures": 0,
                "score": 82
            },
            {
                "uid": 78053166,
                "nick": "\u0413\u0420\u0415\u0428\u041d\u0418\u041a",
                "index": 13,
                "vehicle": "cn_type_58",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 1,
                "captures": 1,
                "score": 370
            },
            {
                "uid": 9212674,
                "nick": "_vavord_",
                "index": 15,
                "vehicle": "spitfire_mk18e",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 1,
                "captures": 0,
                "score": 71
            }
        ]
    }
    team2 = {
        "squadron": "OP2",
        "players": [
            {
                "uid": 147214884,
                "nick": "who_is_Red_Eagle",
                "index": 1,
                "vehicle": "spitfire_lf_mk9e_weisman",
                "vehicle_new": "meow",
                "air_kills": 2,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 1,
                "captures": 0,
                "score": 614
            },
            {
                "uid": 148806865,
                "nick": "\u0413\u0430\u043c\u0431\u0438\u0442\u0412\u043e\u0440\u0411\u043e\u043b\u0442\u043e\u0432",
                "index": 2,
                "vehicle": "germ_pzkpfw_VI_ausf_h1_tiger",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 0,
                "captures": 0,
                "score": 50
            },
            {
                "uid": 1520989,
                "nick": "Red__Eagle",
                "index": 3,
                "vehicle": "spitfire_lf_mk9e_weisman",
                "vehicle_new": "meow",
                "air_kills": 1,
                "ground_kills": 1,
                "assists": 0,
                "deaths": 1,
                "captures": 0,
                "score": 647
            },
            {
                "uid": 158786199,
                "nick": "\u0413\u043b\u0443\u043f\u044b\u0439 \u0417\u0435\u043d\u0438\u0442\u0447\u0438\u043a",
                "index": 4,
                "vehicle": "fr_tpk_641_vpc",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 0,
                "captures": 0,
                "score": 20
            },
            {
                "uid": 199447819,
                "nick": "\u0412\u0441\u043e\u0441\u0430\u043b",
                "index": 5,
                "vehicle": "spitfire_ix",
                "vehicle_new": "meow",
                "air_kills": 1,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 0,
                "captures": 0,
                "score": 299
            },
            {
                "uid": 199627066,
                "nick": "34531",
                "index": 6,
                "vehicle": "tu-2",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 3,
                "assists": 0,
                "deaths": 0,
                "captures": 0,
                "score": 831
            },
            {
                "uid": 38297340,
                "nick": "Mistress BUBA",
                "index": 8,
                "vehicle": "ussr_is_1",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 0,
                "captures": 0,
                "score": 0
            },
            {
                "uid": 88384976,
                "nick": "Glochamba",
                "index": 14,
                "vehicle": "germ_pzkpfw_VI_ausf_h1_tiger",
                "vehicle_new": "meow",
                "air_kills": 0,
                "ground_kills": 0,
                "assists": 0,
                "deaths": 0,
                "captures": 0,
                "score": 30
            }
        ]
    }
    await create_scoreboard(
        match_details={
            "utc_timestamp": '1746424038',
            "session_id": '4acb2a60017e0f6'
        },
        winning_team="9615",
        team1_details=team1,
        team2_details=team2,
        map_file=" [Domination] Abandoned Factory",
        output_path="output.png"
    )

if __name__ == "__main__":
    asyncio.run(test())
