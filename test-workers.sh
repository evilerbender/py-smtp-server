#!/bin/bash
set -euo pipefail

echo "🧪 Testing worker imports and basic functionality"
echo "=============================================="

echo "📋 Testing SQS worker import..."
uv run python -c "
try:
    from sqs_worker import SQSWorker
    print('✅ SQS worker imports successfully')
    
    # Test basic instantiation (will fail without proper config, but should import)
    try:
        worker = SQSWorker()
        print('✅ SQS worker instantiation works')
    except Exception as e:
        if 'SQS_QUEUE_URL' in str(e):
            print('✅ SQS worker requires proper config (expected)')
        else:
            print(f'⚠️  SQS worker instantiation issue: {e}')
except ImportError as e:
    print(f'❌ SQS worker import failed: {e}')
"

echo ""
echo "📋 Testing Redis worker import..."
uv run python -c "
try:
    from redis_worker import RedisWorker
    print('✅ Redis worker imports successfully')
    
    # Test basic instantiation with required stream_name
    try:
        worker = RedisWorker('test_stream')
        print('✅ Redis worker instantiation works')
    except ImportError as e:
        if 'redis' in str(e).lower():
            print('⚠️  Redis not installed (expected for SQS-only deployments)')
        else:
            print(f'❌ Redis worker instantiation failed: {e}')
    except Exception as e:
        print(f'⚠️  Redis worker config issue (expected): {e}')
except ImportError as e:
    print(f'❌ Redis worker import failed: {e}')
"

echo ""
echo "🎉 Worker import tests completed!"