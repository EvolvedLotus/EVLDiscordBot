#!/usr/bin/env python3
"""
Comprehensive test runner for the Discord CMS system
Runs all test suites and generates reports
"""

import sys
import os
import pytest
import time
from datetime import datetime
import json
from pathlib import Path

def setup_test_environment():
    """Setup environment for testing"""
    # Add project root to Python path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    # Set test environment variables
    os.environ.setdefault('TESTING', 'true')
    os.environ.setdefault('JWT_SECRET_KEY', 'test_secret_key_for_testing_only')

    print("✅ Test environment setup complete")

def run_unit_tests():
    """Run unit tests for all components"""
    print("\n🧪 Running Unit Tests...")

    test_files = [
        'tests/test_sync_manager.py',
        'tests/test_auth_manager.py',
        # Add more test files as they are created
    ]

    results = {}
    total_passed = 0
    total_failed = 0

    for test_file in test_files:
        if os.path.exists(test_file):
            print(f"\n📋 Running {test_file}...")
            start_time = time.time()

            # Run pytest on the file
            exit_code = pytest.main([
                test_file,
                '-v',  # verbose output
                '--tb=short',  # shorter traceback
                '--no-header',  # cleaner output
                '--disable-warnings'  # reduce noise
            ])

            end_time = time.time()
            duration = end_time - start_time

            if exit_code == 0:
                results[test_file] = {'status': 'PASSED', 'duration': duration}
                total_passed += 1
                print(f"✅ {test_file} PASSED ({duration:.2f}s)")
            else:
                results[test_file] = {'status': 'FAILED', 'duration': duration}
                total_failed += 1
                print(f"❌ {test_file} FAILED ({duration:.2f}s)")
        else:
            print(f"⚠️  {test_file} not found, skipping")

    return results, total_passed, total_failed

def run_integration_tests():
    """Run integration tests"""
    print("\n🔗 Running Integration Tests...")

    # For now, just run a basic integration test
    integration_tests = [
        'tests/test_integration.py'  # Will be created
    ]

    results = {}
    total_passed = 0
    total_failed = 0

    for test_file in integration_tests:
        if os.path.exists(test_file):
            print(f"\n📋 Running {test_file}...")
            start_time = time.time()

            exit_code = pytest.main([
                test_file,
                '-v',
                '--tb=short',
                '--no-header',
                '--disable-warnings'
            ])

            end_time = time.time()
            duration = end_time - start_time

            if exit_code == 0:
                results[test_file] = {'status': 'PASSED', 'duration': duration}
                total_passed += 1
                print(f"✅ {test_file} PASSED ({duration:.2f}s)")
            else:
                results[test_file] = {'status': 'FAILED', 'duration': duration}
                total_failed += 1
                print(f"❌ {test_file} FAILED ({duration:.2f}s)")
        else:
            print(f"⚠️  {test_file} not found, skipping")

    return results, total_passed, total_failed

def run_performance_tests():
    """Run performance tests"""
    print("\n⚡ Running Performance Tests...")

    # Basic performance test - just check import times for now
    start_time = time.time()

    try:
        # Test core module imports
        import core.sync_manager
        import core.auth_manager
        import core.audit_manager

        # Test backend import
        import backend

        end_time = time.time()
        import_time = end_time - start_time

        print(f"⚡ Import performance: {import_time:.2f}s")
        return {'import_performance': {'status': 'PASSED', 'import_time': import_time}}

    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return {'import_performance': {'status': 'FAILED', 'error': str(e)}}

def generate_test_report(unit_results, integration_results, performance_results, total_passed, total_failed):
    """Generate comprehensive test report"""
    print("\n📊 Generating Test Report...")

    report = {
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_tests': total_passed + total_failed,
            'passed': total_passed,
            'failed': total_failed,
            'success_rate': f"{(total_passed / (total_passed + total_failed) * 100):.1f}%" if (total_passed + total_failed) > 0 else "0%"
        },
        'unit_tests': unit_results,
        'integration_tests': integration_results,
        'performance_tests': performance_results,
        'environment': {
            'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            'platform': sys.platform,
            'test_environment': os.getenv('TESTING', 'false')
        }
    }

    # Save report to file
    report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"📄 Report saved to: {report_file}")

    return report

def print_summary_report(report):
    """Print a human-readable summary"""
    print("\n" + "="*60)
    print("🎯 TEST EXECUTION SUMMARY")
    print("="*60)

    summary = report['summary']
    print(f"Total Tests: {summary['total_tests']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Success Rate: {summary['success_rate']}")

    print(f"\nEnvironment: {report['environment']['python_version']} on {report['environment']['platform']}")

    if summary['failed'] > 0:
        print("\n❌ FAILED TESTS:")
        for test_file, result in report['unit_tests'].items():
            if result['status'] == 'FAILED':
                print(f"  - {test_file}")
        for test_file, result in report['integration_tests'].items():
            if result['status'] == 'FAILED':
                print(f"  - {test_file}")

    print("\n✅ Test execution completed!")

def main():
    """Main test runner function"""
    print("🚀 Starting Discord CMS Test Suite")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Setup test environment
    setup_test_environment()

    # Run different test suites
    unit_results, unit_passed, unit_failed = run_unit_tests()
    integration_results, int_passed, int_failed = run_integration_tests()
    performance_results = run_performance_tests()

    # Calculate totals
    total_passed = unit_passed + int_passed
    total_failed = unit_failed + int_failed

    # Generate and display report
    report = generate_test_report(
        unit_results, integration_results, performance_results,
        total_passed, total_failed
    )

    print_summary_report(report)

    # Return appropriate exit code
    return 0 if total_failed == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
