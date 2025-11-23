"""
Quick verification script to check all slash commands are properly defined
Run this to verify command registration before starting the bot
"""

import os
import sys
import importlib.util

def load_module_from_file(filepath, module_name):
    """Load a Python module from a file path"""
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def count_commands_in_file(filepath):
    """Count @app_commands.command decorators in a file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Count app_commands.command occurrences
    count = content.count('@app_commands.command(')
    return count

def main():
    cogs_dir = os.path.join(os.path.dirname(__file__), 'cogs')
    
    cog_files = {
        'currency.py': 'Currency',
        'admin.py': 'Admin',
        'general.py': 'General',
        'announcements.py': 'Announcements',
        'tasks.py': 'Tasks',
        'bot_admin.py': 'Bot Admin',
        'embeds.py': 'Embeds',
        'ai_cog.py': 'AI',
        'moderation.py': 'Moderation Settings',
        'moderation_commands.py': 'Moderation Commands'
    }
    
    print("=" * 60)
    print("SLASH COMMAND VERIFICATION")
    print("=" * 60)
    print()
    
    total_commands = 0
    
    for filename, cog_name in cog_files.items():
        filepath = os.path.join(cogs_dir, filename)
        
        if not os.path.exists(filepath):
            print(f"❌ {cog_name:25} - FILE NOT FOUND: {filename}")
            continue
        
        command_count = count_commands_in_file(filepath)
        total_commands += command_count
        
        status = "✅" if command_count > 0 else "⚠️"
        print(f"{status} {cog_name:25} - {command_count:2} commands")
    
    print()
    print("=" * 60)
    print(f"TOTAL SLASH COMMANDS: {total_commands}")
    print("=" * 60)
    print()
    
    # Expected count - updated to 77
    expected = 77
    if total_commands == expected:
        print(f"✅ SUCCESS! All {expected} commands are properly defined!")
    elif total_commands < expected:
        print(f"⚠️  WARNING: Found {total_commands} commands, expected {expected}")
        print(f"   Missing {expected - total_commands} commands")
    else:
        print(f"⚠️  WARNING: Found {total_commands} commands, expected {expected}")
        print(f"   {total_commands - expected} extra commands (possible duplicates?)")
    
    print()
    print("Next steps:")
    print("1. Start the bot")
    print("2. Check logs for 'Synced X slash commands'")
    print("3. Type / in Discord to see all commands")
    print()

if __name__ == "__main__":
    main()
