import subprocess
import sys
import os

def run(script):
    print(f"Running {script}...")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode

def run_module(args):
    print(f"Running module: {' '.join(args)}")
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    result = subprocess.run([sys.executable, "-m"] + args, env=env, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode

print("--- Running kg_pipeline init-run ---")
run_module(["kg_pipeline", "init-run", "--run", "llm_rebuild_v2_stage_a_03", "--mode", "inventory"])

print("--- Running kg_pipeline inventory ---")
run_module(["kg_pipeline", "inventory", "--run", "llm_rebuild_v2_stage_a_03", "--verify-inputs"])

print("--- Running kg_pipeline verify Gate A ---")
run_module(["kg_pipeline", "verify", "--run", "llm_rebuild_v2_stage_a_03", "--gate", "A"])

print("--- Running tests ---")
run_module(["pytest", "tests/kg_pipeline/test_input_contracts.py", "tests/kg_pipeline/test_inventory.py", "tests/kg_pipeline/test_gate_a.py"])

