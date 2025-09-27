#!/usr/bin/env python3
"""
Interactive configuration generator for SMTP server
"""

import os
import sys
from typing import Dict, Any, List, Optional
from processors import get_processor_class


class ConfigGenerator:
    """Interactive configuration generator"""
    
    def __init__(self):
        self.config = {}
        self.existing_config = self._load_existing_config()
        
    def _load_existing_config(self) -> Dict[str, str]:
        """Load existing .env file if it exists"""
        config = {}
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
        return config
    
    def _get_default_value(self, key: str) -> Optional[str]:
        """Get default value from existing config"""
        return self.existing_config.get(key)
    
    def _prompt_input(self, prompt: str, default: Optional[str] = None, required: bool = False) -> str:
        """Prompt user for input with optional default"""
        if default:
            prompt_text = f"{prompt} [{default}]: "
        else:
            prompt_text = f"{prompt}: "
            
        while True:
            value = input(prompt_text).strip()
            if not value and default:
                return default
            if not value and required:
                print("This field is required. Please enter a value.")
                continue
            return value
    
    def _show_main_menu(self) -> int:
        """Show main menu and get user selection"""
        print("\n" + "="*50)
        print("SMTP Server Configuration Generator")
        print("="*50)
        
        if self.existing_config:
            print(f"Current config loaded from: .env ({len(self.existing_config)} items)")
        else:
            print("No existing config found")
            
        print("\n1. Basic Configuration (host, port, region)")
        print("2. Email Processing (processors)")
        print("3. Advanced Features (rules, monitoring)")
        print("4. Security Settings (TLS, auth)")
        print("5. Review & Generate Configuration")
        print("6. Exit")
        
        while True:
            try:
                choice = int(input("\nSelect option (1-6): "))
                if 1 <= choice <= 6:
                    return choice
                print("Please enter a number between 1 and 6.")
            except ValueError:
                print("Please enter a valid number.")
    
    def _configure_basic_settings(self):
        """Configure basic SMTP server settings"""
        print("\n--- Basic Configuration ---")
        
        # SMTP Host
        default = self._get_default_value('smtp.host') or self._get_default_value('SMTP_HOST')
        self.config['smtp.host'] = self._prompt_input(
            "SMTP Host", default or "0.0.0.0", required=True
        )
        
        # SMTP Port
        default = self._get_default_value('smtp.port') or self._get_default_value('SMTP_PORT')
        self.config['smtp.port'] = self._prompt_input(
            "SMTP Port", default or "8025", required=True
        )
        
        # Log Level
        default = self._get_default_value('log.level') or self._get_default_value('LOG_LEVEL')
        self.config['log.level'] = self._prompt_input(
            "Log Level (DEBUG/INFO/WARNING/ERROR)", default or "INFO", required=True
        )
        
        # AWS Region
        default = self._get_default_value('aws.region') or self._get_default_value('AWS_REGION')
        self.config['aws.region'] = self._prompt_input(
            "AWS Region", default, required=False
        )
        
        print("Basic configuration completed.")
    
    def _configure_email_processing(self):
        """Configure email processors"""
        print("\n--- Email Processing Configuration ---")
        print("Available processors:")
        print("1. SMTP.com API")
        print("2. SQS Queue")
        print("3. S3 Storage")
        print("4. SES Forwarder")
        print("5. File Storage")
        print("6. SQS+S3 Hybrid")
        
        # For now, implement SMTP.com API as example
        if input("\nConfigure SMTP.com API processor? (y/N): ").lower().startswith('y'):
            self._configure_smtpcom_processor()
    
    def _configure_smtpcom_processor(self):
        """Configure SMTP.com API processor"""
        print("\n--- SMTP.com API Configuration ---")
        
        try:
            processor_class = get_processor_class('smtpcom_api')
            config_spec = processor_class.get_config_spec()
            
            processor_config = {}
            for key, spec in config_spec.items():
                env_key = f"worker.processors.0.{key}"
                default = self._get_default_value(env_key)
                
                value = self._prompt_input(
                    spec['description'],
                    default,
                    required=spec['required']
                )
                
                if value:
                    processor_config[key] = value
            
            # Store processor config
            self.config['worker.processors.0.type'] = 'smtpcom_api'
            for key, value in processor_config.items():
                self.config[f'worker.processors.0.{key}'] = value
                
        except Exception as e:
            print(f"Error configuring SMTP.com processor: {e}")
    
    def _configure_advanced_features(self):
        """Configure advanced features"""
        print("\n--- Advanced Features ---")
        print("Advanced features configuration not yet implemented.")
        # TODO: Implement rule engine, monitoring configuration
    
    def _configure_security_settings(self):
        """Configure security settings"""
        print("\n--- Security Settings ---")
        print("Security settings configuration not yet implemented.")
        # TODO: Implement TLS, authentication configuration
    
    def _review_and_generate(self, clean_output: bool = False):
        """Review configuration and generate output"""
        if not self.config:
            print("\nNo configuration items set. Please configure some settings first.")
            return
            
        print("\n--- Configuration Review ---")
        for key, value in sorted(self.config.items()):
            # Mask sensitive values
            if 'key' in key.lower() or 'password' in key.lower():
                display_value = f"{value[:8]}..." if len(value) > 8 else "***"
            else:
                display_value = value
            print(f"{key} = {display_value}")
        
        if input("\nGenerate configuration? (Y/n): ").lower() not in ['n', 'no']:
            self._output_config(clean_output)
    
    def _output_config(self, clean_output: bool = False):
        """Output configuration to stdout"""
        if not clean_output:
            print("\n# =============================================================================")
            print("# SMTP Server Configuration")
            print("# Generated by interactive configuration tool")
            print("# =============================================================================")
        
        # Group by category for organized output
        basic_keys = ['smtp.host', 'smtp.port', 'log.level', 'aws.region']
        processor_keys = [k for k in self.config.keys() if 'processors' in k]
        other_keys = [k for k in self.config.keys() if k not in basic_keys and k not in processor_keys]
        
        # Output basic configuration
        if not clean_output and any(k in self.config for k in basic_keys):
            print("\n# Basic Configuration")
        for key in basic_keys:
            if key in self.config:
                print(f"{key}={self.config[key]}")
        
        # Output processor configuration
        if not clean_output and processor_keys:
            print("\n# Email Processors")
        for key in sorted(processor_keys):
            print(f"{key}={self.config[key]}")
        
        # Output other configuration
        if not clean_output and other_keys:
            print("\n# Other Settings")
        for key in sorted(other_keys):
            print(f"{key}={self.config[key]}")
        
        # Add TODOs for non-dot-notation items
        if not clean_output:
            print("\n# TODO: Convert remaining items to dot-notation format")
    
    def run(self, clean_output: bool = False):
        """Run the interactive configuration generator"""
        try:
            while True:
                choice = self._show_main_menu()
                
                if choice == 1:
                    self._configure_basic_settings()
                elif choice == 2:
                    self._configure_email_processing()
                elif choice == 3:
                    self._configure_advanced_features()
                elif choice == 4:
                    self._configure_security_settings()
                elif choice == 5:
                    self._review_and_generate(clean_output)
                elif choice == 6:
                    print("Exiting configuration generator.")
                    break
                    
        except KeyboardInterrupt:
            print("\n\nConfiguration generator interrupted.")
            sys.exit(1)


def main():
    """Main entry point for configuration generator"""
    clean_output = '--clean' in sys.argv
    generator = ConfigGenerator()
    generator.run(clean_output)


if __name__ == '__main__':
    main()
