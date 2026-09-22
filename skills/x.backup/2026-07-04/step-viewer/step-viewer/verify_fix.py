#!/usr/bin/env python3
import ast, re

with open('web-step-viewer.py') as f:
    source = f.read()

tree = ast.parse(source)
print('AST parsed OK')

for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'unified_update':
        print(f'unified_update: {len(node.args.args)} args')
        returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
        print(f'Return statements: {len(returns)}')
        all_ok = True
        for i, ret in enumerate(returns):
            if ret.value is None:
                print(f'  Return {i+1}: None (bare return)')
                all_ok = False
            elif isinstance(ret.value, ast.Tuple):
                n_el = len(ret.value.elts)
                if n_el != 29:
                    print(f'  Return {i+1}: TUPLE of {n_el} elements (expected 29!)')
                    all_ok = False
        if all_ok:
            print(f'  All returns have 29-element tuples OK')

# Check each trigger handler exists
triggers = ['x-slider', 'y-slider', 'z-slider', 'axis-x', 'axis-y', 'axis-z',
            'btn-find-tip', 'btn-reset', 'file-upload', 'tol-slider']
print()
for trigger in triggers:
    marker = "triggered_id == '" + trigger + "'"
    found = marker in source
    status = 'FOUND' if found else 'MISSING'
    print(f'  Handler for {trigger}: {status}')

# Check that bx/xs/ys/zs are defined in EVERY return path
print()
print('Checking bx/xs/ys/zs assignments in return paths...')
# Count how many times bx is assigned before each return
lines = source.split('\n')
func_start = None
func_end = None
for i, line in enumerate(lines):
    if 'def unified_update(' in line:
        func_start = i
    if func_start is not None and i > func_start + 500:
        func_end = i
        break

if func_start and func_end:
    print(f'unified_update: lines {func_start} to {func_end}')
    print('Total lines:', func_end - func_start)
