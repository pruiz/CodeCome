#!/usr/bin/env python3
"""
E2E workflow test script.
Orchestrates the aimock server, runs CodeCome phases, and compares JSON output/artifacts.
"""

import os
import sys
import json
import shutil
import subprocess

def run_cmd(cmd, env=None, capture=True):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, env=env, text=True, capture_output=capture)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}:\n{result.stderr}")
        sys.exit(result.returncode)
    return result.stdout

def setup_workspace():
    print("Setting up workspace...")
    run_cmd("make itemdb-reset", capture=False)
    
    # Ensure src directory exists and is empty
    if os.path.exists("src"):
        shutil.rmtree("src")
    shutil.copytree("tests/fixtures/sample-c-cli", "src")
    
def compare_json_streams(baseline_path, actual_output):
    if not os.path.exists(baseline_path):
        print(f"Warning: Baseline {baseline_path} does not exist. Skipping exact JSON comparison.")
        return

    with open(baseline_path, "r") as f:
        baseline_lines = [line.strip() for line in f if line.strip()]
        
    actual_lines = [line.strip() for line in actual_output.split("\n") if line.strip()]
    
    # Very basic comparison: check if the sequence of event types match
    # (ignoring text/tool_use ordering within a single step)
    def group_events_by_step(lines):
        steps = []
        current_step = []
        for line in lines:
            try:
                data = json.loads(line)
                event_type = data.get("type")
                if event_type == "step_start":
                    current_step = [event_type]
                elif event_type == "step_finish":
                    current_step.append(event_type)
                    steps.append(current_step)
                    current_step = []
                elif event_type in ("text", "tool_use"):
                    current_step.append(event_type)
                else:
                    # ignore other top-level events (e.g. error) for structure
                    pass
            except json.JSONDecodeError:
                pass
        return steps

    baseline_steps = group_events_by_step(baseline_lines)
    actual_steps = group_events_by_step(actual_lines)

    if len(baseline_steps) != len(actual_steps):
        print("ERROR: Step count mismatch!")
        print(f"Expected steps: {len(baseline_steps)}")
        print(f"Actual steps:   {len(actual_steps)}")
        sys.exit(1)

    mismatched = False
    for i, (b_step, a_step) in enumerate(zip(baseline_steps, actual_steps)):
        # Within a step, text and tool_use ordering is non-deterministic,
        # but the counts and the relative order of tool_use events matter.
        if b_step[0] != "step_start" or a_step[0] != "step_start":
            mismatched = True
            print(f"ERROR: Step {i+1} missing step_start!")
            print(f"  Expected: {b_step}")
            print(f"  Actual:   {a_step}")
            break
        if b_step[-1] != "step_finish" or a_step[-1] != "step_finish":
            mismatched = True
            print(f"ERROR: Step {i+1} missing step_finish!")
            print(f"  Expected: {b_step}")
            print(f"  Actual:   {a_step}")
            break
        b_inner = b_step[1:-1]
        a_inner = a_step[1:-1]
        if b_inner != a_inner:
            # Allow if only text/tool_use positions differ (same counts)
            b_tools = [e for e in b_inner if e == "tool_use"]
            a_tools = [e for e in a_inner if e == "tool_use"]
            b_texts = b_inner.count("text")
            a_texts = a_inner.count("text")
            if b_tools != a_tools or b_texts != a_texts:
                mismatched = True
                print(f"ERROR: Step {i+1} event mismatch!")
                print(f"  Expected: {b_step}")
                print(f"  Actual:   {a_step}")
                break

    if mismatched:
        sys.exit(1)
    else:
        print(f"JSON stream event types match step-by-step ({len(baseline_steps)} steps).")

def main():
    # 1. Stop and start server
    run_cmd("make e2e-server-stop", capture=False)
    run_cmd("make e2e-server-start", capture=False)
    
    try:
        # 2. Setup
        setup_workspace()
        
        # 3. Run Phase 1
        env = os.environ.copy()
        env["CODECOME_USE_WRAPPER"] = "0"
        
        model_to_use = os.environ.get("AIMOCK_MODEL", "minimax/minimax-m2.5:free")
        env["OPENCODE_ARGS"] = f"--format json -m aimock/{model_to_use}"
        env["CODECOME_MODEL"] = f"aimock/{model_to_use}"
        
        print("Running Phase 1...")
        stdout = run_cmd("make phase-1", env=env)
        
        # 4. Compare JSON
        baseline_file = "tests/fixtures/recordings/phase-1.json"
        compare_json_streams(baseline_file, stdout)
        
        # 5. Assert File Artifacts
        print("Checking artifacts...")
        if not os.path.exists("itemdb/notes/target-profile.md"):
            print("ERROR: target-profile.md was not generated.")
            sys.exit(1)
            
        print("E2E Test completed successfully.")
        
    finally:
        # Clean up server
        run_cmd("make e2e-server-stop", capture=False)

if __name__ == "__main__":
    main()
