#!/bin/bash
# Verification script for the hardcoded Qlib path fix
# Usage: bash verify_fix.sh

set -e

echo "🔍 Verifying hardcoded Qlib path fix..."
echo ""

# Check if Python files were modified
echo "1️⃣  Checking qlib_runner.py for symlink setup..."
if grep -q "_setup_qlib_data_symlinks" src/runner/qlib_runner.py; then
    echo "   ✅ Found _setup_qlib_data_symlinks function"
else
    echo "   ❌ Missing _setup_qlib_data_symlinks function"
    exit 1
fi

if grep -q "_setup_qlib_data_symlinks(config)" src/runner/qlib_runner.py; then
    echo "   ✅ Function is called in run_rdagent()"
else
    echo "   ❌ Function is not called"
    exit 1
fi

# Check patch modules exist
echo ""
echo "2️⃣  Checking backup patch modules..."
if [ -f src/runner/patch_generated_code.py ]; then
    echo "   ✅ patch_generated_code.py exists"
else
    echo "   ⚠️  patch_generated_code.py not found (backup)"
fi

if [ -f src/runner/patch_monitor.py ]; then
    echo "   ✅ patch_monitor.py exists"
else
    echo "   ⚠️  patch_monitor.py not found (backup)"
fi

# Syntax check
echo ""
echo "3️⃣  Checking Python syntax..."
python -m py_compile src/runner/qlib_runner.py
echo "   ✅ qlib_runner.py syntax OK"

python -m py_compile src/runner/patch_generated_code.py
echo "   ✅ patch_generated_code.py syntax OK"

python -m py_compile src/runner/patch_monitor.py
echo "   ✅ patch_monitor.py syntax OK"

# Check symlink targets are comprehensive
echo ""
echo "4️⃣  Checking symlink targets..."
targets=$(grep -o 'Path.home() / ".qlib"' src/runner/qlib_runner.py | wc -l)
if [ "$targets" -ge 1 ]; then
    echo "   ✅ Found ~/.qlib targets ($targets)"
fi

# Summary
echo ""
echo "✨ Verification complete!"
echo ""
echo "NEXT STEPS:"
echo "1. Run: python -m src.main run"
echo "2. Check logs for 'Created symlink' messages"
echo "3. Verify ~/.qlib/qlib_data/cn_data symlink exists"
echo "4. Verify discovered_factors.yaml is generated"
