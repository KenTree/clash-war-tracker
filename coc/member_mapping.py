# coc/member_mapping.py
"""
Handles mapping between Clash of Clans player tags and Discord user IDs.
This allows the bot to ping the correct Discord users when members need to attack.
"""
from typing import Dict, Optional
import json
import os


class MemberMapper:
    """Maps CoC player tags to Discord user IDs"""
    
    def __init__(self, mapping_file: str = "member_mappings.json"):
        self.mapping_file = mapping_file
        self.mappings: Dict[str, int] = {}
        self.load_mappings()
    
    def load_mappings(self):
        """Load mappings from JSON file"""
        if os.path.exists(self.mapping_file):
            try:
                with open(self.mapping_file, 'r') as f:
                    data = json.load(f)
                    # Convert string IDs back to integers
                    self.mappings = {k: int(v) for k, v in data.items()}
                print(f"Loaded {len(self.mappings)} member mappings")
            except Exception as e:
                print(f"Error loading mappings: {e}")
                self.mappings = {}
        else:
            print("No mapping file found. Starting with empty mappings.")
            self.mappings = {}
    
    def save_mappings(self):
        """Save mappings to JSON file"""
        try:
            with open(self.mapping_file, 'w') as f:
                json.dump(self.mappings, f, indent=2)
            print(f"Saved {len(self.mappings)} member mappings")
        except Exception as e:
            print(f"Error saving mappings: {e}")
    
    def add_mapping(self, coc_tag: str, discord_id: int) -> bool:
        """
        Add a mapping between CoC player tag and Discord user ID
        
        Args:
            coc_tag: Clash of Clans player tag (e.g., "#ABC123")
            discord_id: Discord user ID (integer)
        
        Returns:
            True if mapping was added successfully
        """
        # Normalize the tag (ensure it starts with #)
        if not coc_tag.startswith("#"):
            coc_tag = f"#{coc_tag}"
        
        self.mappings[coc_tag] = discord_id
        self.save_mappings()
        return True
    
    def remove_mapping(self, coc_tag: str) -> bool:
        """Remove a mapping by CoC tag"""
        if not coc_tag.startswith("#"):
            coc_tag = f"#{coc_tag}"
        
        if coc_tag in self.mappings:
            del self.mappings[coc_tag]
            self.save_mappings()
            return True
        return False
    
    def get_discord_id(self, coc_tag: str) -> Optional[int]:
        """Get Discord ID for a given CoC tag"""
        if not coc_tag.startswith("#"):
            coc_tag = f"#{coc_tag}"
        return self.mappings.get(coc_tag)
    
    def get_all_mappings(self) -> Dict[str, int]:
        """Get all mappings"""
        return self.mappings.copy()
    
    def is_mapped(self, coc_tag: str) -> bool:
        """Check if a CoC tag has a Discord mapping"""
        if not coc_tag.startswith("#"):
            coc_tag = f"#{coc_tag}"
        return coc_tag in self.mappings