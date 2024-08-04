# Discord Bot for War Thunder

This is a Discord bot designed for War Thunder, providing various features such as squadron management, game logging, and vehicle meta-management.

## Usage

### Prerequisites

- Python 3.10 or higher
- Poetry for package management

### Installation

1. Clone the repository to your local machine.

    ```sh
    git clone <repository_url>
    cd <repository_directory>
    ```

2. Install the dependencies using Poetry.

    ```sh
    poetry install
    ```

3. Set your Discord bot token in the environment variable `TEST_DISCORD_KEY`.

    ```sh
    export DISCORD_KEY=your_discord_bot_token
    ```

### Running the Bot

You can start the bot by running `BotScript.py`.

```sh
poetry run python BotScript.py
```


### Commands Overview

/grant [target] [permission_type] - Grant a user or role permission.
/revoke [target] [permission_type] - Revoke a user or role's permission.
/clear - Clear the entire Meta list (Owner only).
/session - Start a new session.
/win [team_name] [bombers] [fighters] [helis] [tanks] [spaa] [comment] - Log a win for a team.
/loss [team_name] [bombers] [fighters] [helis] [tanks] [spaa] [comment] - Log a loss for a team.
/end - End the current session.
/edit [status] [team_name] [bombers] [fighters] [helis] [tanks] [spaa] [comment] - Edit the details of the last logged game.
/quick-log [status] [enemy team name] - Quickly log a game using vehicle data from the game log.
/loop [url] - Create a GIF from the last image posted or a provided URL.
/bubble [url] - Create a GIF with an empty speech bubble from the last image posted or a provided URL.
/alarm [type] [channel_id] [squadron_name] - Set an alarm to monitor squadron changes.
/stat [username] - Get the ThunderSkill stats URL for a user.
/guessing-game - Start a guessing game.
/trivia [difficulty] - Play a War Thunder vehicle trivia game. A higher difficulty means more points.
/leaderboard - Show the leaderboard.
/console - Choose an action (Add or Remove vehicles).
/help - Get a guide on how to use the bot.
File Overview
The main script that runs the Discord bot. It includes setup, command definitions, event handlers, and helper functions.

Handles taking, saving, loading, and comparing snapshots of squadron members and their points. It includes the following key functions:

take_snapshot()
save_snapshot()
load_snapshot()
compare_snapshots()
A helper script to count lines of code in the project, excluding certain directories and files. Defines the function:

Includes functionality for parsing game logs and events. Defines the EventType class.

### Features
Meta Management
Allows users to add, remove, and view vehicles in the Meta list based on their Battle Ratings (BR).

Alarms
Monitor squadron changes and notify when members leave with points.

Game Logging
Log game outcomes (wins, losses) along with details like the enemy team name, vehicle counts, and comments.

Interactive Commands
Use Discord's UI components like modals and dropdowns to interact with the bot.

### License
This project is licensed under the MIT License. See the LICENSE file for details.

