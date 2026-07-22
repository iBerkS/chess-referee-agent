import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from agent import ChessAgent
from scenarios import SCENARIOS

STATUS_MAP = {"PASSED": "GEÇTİ", "FAILED": "KALDI", "INVALID": "GEÇERSİZ"}

REPEAT_COUNT = 5


def run(repeat_count=REPEAT_COUNT):
    # key: (scenario_id, check_name) -> {"category": str, "runs": [{"status", "detail"}, ...]}
    results_by_check = {}

    for scenario in SCENARIOS:
        for _ in range(repeat_count):
            agent = ChessAgent(fen=scenario["start_fen"])

            if "user_prompts" in scenario:
                final_answer = None
                for prompt in scenario["user_prompts"]:
                    final_answer = agent.ask(prompt)
            else:
                final_answer = agent.ask(scenario["user_prompt"])

            for check_name, check_fn in scenario["check_fns"].items():
                status, detail = check_fn(agent, final_answer)
                key = (scenario["id"], check_name)
                entry = results_by_check.setdefault(key, {"category": scenario["category"], "runs": []})
                entry["runs"].append({"status": status, "detail": detail})

            agent.close()

    print(f"\n=== EVAL SONUÇLARI (istatistiksel özet, N={repeat_count} koşum) ===")

    combo_pass_rates = []
    for (scenario_id, check_name), entry in results_by_check.items():
        runs = entry["runs"]
        category = entry["category"]
        n = len(runs)
        passed = sum(1 for r in runs if r["status"] == "PASSED")
        failed = sum(1 for r in runs if r["status"] == "FAILED")
        invalid = sum(1 for r in runs if r["status"] == "INVALID")
        testable = n - invalid

        if testable == 0:
            rate_str = "N/A (hiç test edilemedi)"
            pass_rate = None
        else:
            pass_pct = 100 * passed / testable
            rate_str = f"{passed}/{testable} GEÇTİ (test edilebilirler üzerinden %{pass_pct:.0f})"
            pass_rate = pass_pct

        print(f"\n{scenario_id} / {check_name} ({category}): {passed}/{n} GEÇTİ, {failed}/{n} KALDI, {invalid}/{n} GEÇERSİZ")
        print(f"  -> {rate_str}")

        failed_example = next((r["detail"] for r in runs if r["status"] == "FAILED"), None)
        invalid_example = next((r["detail"] for r in runs if r["status"] == "INVALID"), None)
        if failed_example:
            print(f"  örnek (KALDI): {failed_example}")
        if invalid_example:
            print(f"  örnek (GEÇERSİZ): {invalid_example}")

        combo_pass_rates.append(pass_rate)

    print("\n=== GENEL DAĞILIM ===")
    total_combos = len(combo_pass_rates)
    high = sum(1 for r in combo_pass_rates if r is not None and r >= 80)
    mid = sum(1 for r in combo_pass_rates if r is not None and 50 <= r < 80)
    low = sum(1 for r in combo_pass_rates if r is not None and r < 50)
    na = sum(1 for r in combo_pass_rates if r is None)
    print(f"Toplam {total_combos} (senaryo, kontrol) kombinasyonu:")
    print(f"  %80+ PASSED oranı: {high}")
    print(f"  %50-80 PASSED oranı: {mid}")
    print(f"  %50 altı PASSED oranı: {low}")
    print(f"  N/A (hiç test edilemedi): {na}")


if __name__ == "__main__":
    repeat_count = REPEAT_COUNT
    if len(sys.argv) > 1:
        try:
            repeat_count = int(sys.argv[1])
        except ValueError:
            pass
    run(repeat_count)
