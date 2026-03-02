import yaml
import os

class BuoyConfig:
    def __init__(self, config_path="buoy_config.yaml"):
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
            
        with open(config_path, 'r') as f:
            self.cfg = yaml.safe_load(f)
            
    def get_config_for_id(self, buoy_id):
        """
        Iterates through configured types to find the BEST match for the buoy_id.
        Prioritizes the longest matching pattern (most specific).
        """
        best_match = None
        best_len = 0
        
        for type_name, settings in self.cfg['buoy_types'].items():
            pattern = settings.get('match_pattern')
            if pattern and pattern in buoy_id:
                # If this pattern is more specific (longer) than the previous best, take it
                if len(pattern) > best_len:
                    best_match = settings
                    best_match['type_name'] = type_name # Inject name for debug
                    best_len = len(pattern)
        
        if best_match:
            return best_match
        
        raise ValueError(f"No configuration found matching Buoy ID: {buoy_id}")

    def get_defaults(self):
        return self.cfg.get('defaults', {})