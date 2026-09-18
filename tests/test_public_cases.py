import json
import requests
import os
import time

SAMPLES_FILE = "../BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
URL = "https://bup-prelim.onrender.com/optimize-energy"

def run_tests():
    with open(SAMPLES_FILE, "r") as f:
        data = json.load(f)

    cases = data.get("cases", [])
    if not cases:
        print("No cases found in file.")
        return

    passed = 0
    failed = 0

    for i, case in enumerate(cases):
        print(f"\n--- Running Case {i+1}/{len(cases)}: {case['id']} - {case['label']} ---")
        
        try:
            # Check the API
            start_time = time.time()
            response = requests.post(URL, json=case["input"])
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            if response.status_code != 200:
                print(f"[FAIL] API Error: HTTP {response.status_code}")
                print(response.text)
                failed += 1
                continue
            
            result = response.json()
            expected = case["expected_output"]
            
            print(f"Response time: {elapsed_time:.2f} seconds")
            
            # 1. Check interpretations
            print("Interpretations:")
            for interp in result["directive_interpretation"]:
                print(f"  - {interp['directive_type']} (applies={interp['applies']}): {interp['structured_adjustment']}")
                
            # 2. Check cost match (within 0.01 tolerance)
            cost_diff = abs(result["total_cost_bdt"] - expected["total_cost_bdt"])
            
            print(f"Cost returned: {result['total_cost_bdt']} BDT")
            print(f"Cost expected: {expected['total_cost_bdt']} BDT")
            
            if cost_diff <= 0.01:
                print("[PASS] Cost matches expected!")
                passed += 1
            else:
                print(f"[FAIL] Cost mismatch (diff: {cost_diff:.4f})")
                failed += 1
                
        except Exception as e:
            print(f"[FAIL] Test script error: {e}")
            failed += 1
            
    print(f"\n=== TEST RUN COMPLETE ===")
    print(f"Passed: {passed}/{len(cases)}")
    print(f"Failed: {failed}/{len(cases)}")

if __name__ == "__main__":
    run_tests()
