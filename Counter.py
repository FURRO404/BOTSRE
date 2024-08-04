import os

def count_lines_of_code(directory, script_name):
    total_lines = 0
    log_entries = []

    for root, dirs, files in os.walk(directory):
        # Skip the DATA folder and any .directories
        dirs[:] = [d for d in dirs if d != 'DATA' and not d.startswith('.')]

        for file in files:
            if file.endswith('.py') and file != script_name and not any(part.startswith('.') for part in os.path.relpath(os.path.join(root, file), directory).split(os.sep)):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_lines = sum(1 for _ in f)
                    total_lines += file_lines
                    log_entries.append((file_path, file_lines))

    return total_lines, log_entries

# Use the current directory as the project directory
project_directory = os.getcwd()
script_name = os.path.basename(__file__)
total_lines, log_entries = count_lines_of_code(project_directory, script_name)

# Log each file and their LOC
for file_path, loc in log_entries:
    print(f'{file_path}: {loc} lines')

print(f'\nTotal lines of code: {total_lines}')
