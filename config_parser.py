#!/usr/bin/env python3
"""
Configuration parser for dot-notation environment variables
"""

import os
from typing import Dict, List, Any


def parse_dot_notation_env() -> Dict[str, Any]:
    """
    Parse environment variables with dot notation into nested dictionary
    
    Example:
        email.processors.0.type=smtpcom_api
        email.processors.0.api_key=key123
        
    Returns:
        {
            "email": {
                "processors": [
                    {"type": "smtpcom_api", "api_key": "key123"}
                ]
            }
        }
    """
    result = {}
    
    # Get all environment variables with dots
    dot_vars = {k: v for k, v in os.environ.items() if '.' in k}
    
    for key, value in dot_vars.items():
        parts = key.split('.')
        current = result
        
        # Navigate/create nested structure
        for i, part in enumerate(parts[:-1]):
            if part.isdigit():
                # Array index - current should be a list
                idx = int(part)
                if not isinstance(current, list):
                    # This shouldn't happen with proper structure
                    continue
                # Extend list if needed
                while len(current) <= idx:
                    current.append({})
                current = current[idx]
            else:
                # Object key
                if part not in current:
                    # Look ahead to see if next part is numeric (array)
                    next_part = parts[i + 1] if i + 1 < len(parts) else None
                    if next_part and next_part.isdigit():
                        current[part] = []
                    else:
                        current[part] = {}
                current = current[part]
        
        # Set final value
        final_key = parts[-1]
        current[final_key] = value
    
    return result


def load_processors(config_key: str) -> List[Dict[str, Any]]:
    """
    Load processors from dot-notation config
    
    Args:
        config_key: Either 'email' or 'worker'
        
    Returns:
        List of processor configurations
    """
    config = parse_dot_notation_env()
    if config_key in config and 'processors' in config[config_key]:
        processors_list = config[config_key]['processors']
        # Convert to expected format
        result = []
        for proc in processors_list:
            if 'type' in proc:
                proc_config = {k: v for k, v in proc.items() if k != 'type'}
                result.append({
                    'type': proc['type'],
                    'config': proc_config
                })
        return result
    
    return []


if __name__ == '__main__':
    # Test the parser
    import pprint
    config = parse_dot_notation_env()
    pprint.pprint(config)
