#!/usr/bin/env bash
set -euo pipefail

echo "🧪 Running SMTP Server Test Suite"
echo "=================================="

# Run local tests (no external dependencies)
echo "📋 Running local tests..."
uv run python -c "
import os
import sys
import tempfile
import asyncio
from email.message import EmailMessage

def test_multiple_processors():
    print('Testing multiple processors...')
    
    # Set up multiple processors of different types
    test_vars = {
        'email.processors.0.type': 'file_storage',
        'email.processors.0.storage_dir': '/tmp/test1',
        'email.processors.1.type': 'file_storage', 
        'email.processors.1.storage_dir': '/tmp/test2',
        'worker.processors.0.type': 'file_storage',
        'worker.processors.0.storage_dir': '/tmp/worker1',
        'worker.processors.1.type': 'file_storage',
        'worker.processors.1.storage_dir': '/tmp/worker2',
        'worker.processors.2.type': 'file_storage',
        'worker.processors.2.storage_dir': '/tmp/worker3'
    }
    
    # Backup original env
    original_env = {}
    for key in test_vars:
        if key in os.environ:
            original_env[key] = os.environ[key]
        os.environ[key] = test_vars[key]
    
    try:
        from config_parser import load_processors
        
        # Test email processors (2 processors)
        email_procs = load_processors('email')
        assert len(email_procs) == 2, f'Expected 2 email processors, got {len(email_procs)}'
        assert email_procs[0]['type'] == 'file_storage'
        assert email_procs[1]['type'] == 'file_storage'
        assert email_procs[0]['config']['storage_dir'] == '/tmp/test1'
        assert email_procs[1]['config']['storage_dir'] == '/tmp/test2'
        
        # Test worker processors (3 processors)
        worker_procs = load_processors('worker')
        assert len(worker_procs) == 3, f'Expected 3 worker processors, got {len(worker_procs)}'
        assert all(p['type'] == 'file_storage' for p in worker_procs)
        
        # Test SMTP server creation with multiple processors
        from smtp_server import create_processors
        processors = create_processors()
        assert len(processors) == 2, f'Expected 2 SMTP processors, got {len(processors)}'
        
        print('✅ Multiple processors test passed')
        
    finally:
        # Restore environment
        for key in test_vars:
            if key in original_env:
                os.environ[key] = original_env[key]
            else:
                os.environ.pop(key, None)

def test_mixed_processor_types():
    print('Testing mixed processor types...')
    
    # Set up different processor types (simulated)
    test_vars = {
        'worker.processors.0.type': 'file_storage',
        'worker.processors.0.storage_dir': '/tmp/files',
        'worker.processors.1.type': 'smtpcom_api',
        'worker.processors.1.api_key': 'test_key_1',
        'worker.processors.1.channel': 'channel_1',
        'worker.processors.2.type': 'smtpcom_api', 
        'worker.processors.2.api_key': 'test_key_2',
        'worker.processors.2.channel': 'channel_2'
    }
    
    original_env = {}
    for key in test_vars:
        if key in os.environ:
            original_env[key] = os.environ[key]
        os.environ[key] = test_vars[key]
    
    try:
        from config_parser import load_processors
        
        worker_procs = load_processors('worker')
        assert len(worker_procs) == 3, f'Expected 3 processors, got {len(worker_procs)}'
        
        # Check first processor (file_storage)
        assert worker_procs[0]['type'] == 'file_storage'
        assert worker_procs[0]['config']['storage_dir'] == '/tmp/files'
        
        # Check second processor (smtpcom_api)
        assert worker_procs[1]['type'] == 'smtpcom_api'
        assert worker_procs[1]['config']['api_key'] == 'test_key_1'
        assert worker_procs[1]['config']['channel'] == 'channel_1'
        
        # Check third processor (smtpcom_api with different config)
        assert worker_procs[2]['type'] == 'smtpcom_api'
        assert worker_procs[2]['config']['api_key'] == 'test_key_2'
        assert worker_procs[2]['config']['channel'] == 'channel_2'
        
        print('✅ Mixed processor types test passed')
        
    finally:
        # Restore environment
        for key in test_vars:
            if key in original_env:
                os.environ[key] = original_env[key]
            else:
                os.environ.pop(key, None)

def test_processor_instantiation():
    print('Testing processor instantiation with multiple configs...')
    
    with tempfile.TemporaryDirectory() as temp_dir1, tempfile.TemporaryDirectory() as temp_dir2:
        from processors import FileStorageProcessor
        
        # Create multiple processors with different configs
        proc1 = FileStorageProcessor({'storage_dir': temp_dir1})
        proc2 = FileStorageProcessor({'storage_dir': temp_dir2})
        
        assert str(proc1.storage_dir) == temp_dir1
        assert str(proc2.storage_dir) == temp_dir2
        assert proc1.get_name() == 'FileStorage'
        assert proc2.get_name() == 'FileStorage'
        
        # Test they work independently
        msg = EmailMessage()
        msg['From'] = 'test@example.com'
        msg['To'] = 'recipient@example.com'
        msg['Subject'] = 'Test'
        msg.set_content('Test content')
        
        class MockEnvelope:
            def __init__(self):
                self.mail_from = 'test@example.com'
                self.rcpt_tos = ['recipient@example.com']
        
        envelope = MockEnvelope()
        
        # Process with both processors
        result1 = asyncio.run(proc1.process(envelope, msg))
        result2 = asyncio.run(proc2.process(envelope, msg))
        
        assert result1 == True
        assert result2 == True
        
        # Check files created in different directories
        files1 = os.listdir(temp_dir1)
        files2 = os.listdir(temp_dir2)
        
        assert len(files1) == 1
        assert len(files2) == 1
        assert files1[0] != files2[0]  # Different filenames
        
        print('✅ Processor instantiation test passed')

# Run all tests
print('🧪 Testing multiple processor configurations...')
test_multiple_processors()
test_mixed_processor_types()
test_processor_instantiation()
print('🎉 All multiple processor tests passed!')
"

echo ""
echo "🔍 Running syntax checks..."

# Check Python syntax
echo "  - Checking Python syntax..."
uv run python -m py_compile smtp_server.py
uv run python -m py_compile sqs_worker.py
uv run python -m py_compile config_parser.py
uv run python -m py_compile processors/*.py

echo "  - Checking imports..."
uv run python -c "
import smtp_server
import sqs_worker
import config_parser
from processors import *
print('  ✅ All imports successful')
"

echo ""
echo "🎯 Running configuration validation..."

# Test configuration loading
uv run python -c "
import os
os.environ['email.processors.0.type'] = 'file_storage'
os.environ['email.processors.0.storage_dir'] = './test'
from smtp_server import create_processors
processors = create_processors()
print(f'  ✅ Created {len(processors)} processors')
"

echo ""
echo "🎉 All tests passed! System is ready for deployment."
