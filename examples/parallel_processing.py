"""
Exemple v0.4.0 : Exécution parallèle avec ParallelRunner

Démontre WorkflowEngine(parallel=True) qui utilise ParallelRunner +
concurrent.futures pour exécuter simultanément les steps sans dépendances
mutuelles. Compare aussi les durées séquentielle vs parallèle.

Structure du DAG :
    load_data
    ├── regional_analysis  ┐ groupe parallèle
    └── product_analysis   ┘
         └── final_report
"""

import time
import random
from pyworkflow_engine import WorkflowEngine, Job, Step, StepType, WorkflowContext


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def load_dataset(context: WorkflowContext) -> dict:
    """Charge le dataset initial (simulé)."""
    print("  [load_data] Chargement du dataset...")
    time.sleep(0.1)
    dataset = {
        "sales_data": [
            {
                "id": i,
                "product": f"Produit-{i % 5}",
                "amount": round(random.uniform(10, 500), 2),
                "region": random.choice(["Nord", "Sud", "Est", "Ouest"]),
            }
            for i in range(60)
        ],
        "total_records": 60,
    }
    print(f"  [load_data] {dataset['total_records']} enregistrements chargés")
    return dataset


def analyze_regions(context: WorkflowContext) -> dict:
    """Analyse les ventes par région (step parallèle)."""
    print("  [regional_analysis] Début...")
    time.sleep(0.4)  # Simule un traitement I/O-bound
    dataset = context.get_step_output("load_data")
    stats: dict = {}
    for record in dataset["sales_data"]:
        r = record["region"]
        stats.setdefault(r, {"count": 0, "total": 0.0})
        stats[r]["count"] += 1
        stats[r]["total"] += record["amount"]
    print(f"  [regional_analysis] {len(stats)} régions analysées")
    return {"regional_stats": stats}


def analyze_products(context: WorkflowContext) -> dict:
    """Analyse les ventes par produit (step parallèle)."""
    print("  [product_analysis] Début...")
    time.sleep(0.5)  # Un peu plus long pour montrer le gain parallèle
    dataset = context.get_step_output("load_data")
    stats: dict = {}
    for record in dataset["sales_data"]:
        p = record["product"]
        stats.setdefault(p, {"count": 0, "total": 0.0})
        stats[p]["count"] += 1
        stats[p]["total"] += record["amount"]
    print(f"  [product_analysis] {len(stats)} produits analysés")
    return {"product_stats": stats}


def generate_report(context: WorkflowContext) -> dict:
    """Consolide les deux analyses en un rapport final."""
    print("  [final_report] Génération du rapport...")
    regional = context.get_step_output("regional_analysis")
    products = context.get_step_output("product_analysis")

    top_region = max(regional["regional_stats"].items(), key=lambda x: x[1]["total"])
    top_product = max(products["product_stats"].items(), key=lambda x: x[1]["total"])

    report = {
        "top_region": {"name": top_region[0], "sales": round(top_region[1]["total"], 2)},
        "top_product": {"name": top_product[0], "sales": round(top_product[1]["total"], 2)},
        "regions_count": len(regional["regional_stats"]),
        "products_count": len(products["product_stats"]),
    }
    print(f"  [final_report] Top région : {top_region[0]}, Top produit : {top_product[0]}")
    return report


# ---------------------------------------------------------------------------
# Job definition
# ---------------------------------------------------------------------------

def build_job() -> Job:
    return Job(
        name="Analytics Pipeline",
        steps=[
            Step(name="load_data",          step_type=StepType.FUNCTION, handler=load_dataset),
            Step(name="regional_analysis",  step_type=StepType.FUNCTION, handler=analyze_regions,
                 dependencies=["load_data"]),
            Step(name="product_analysis",   step_type=StepType.FUNCTION, handler=analyze_products,
                 dependencies=["load_data"]),
            Step(name="final_report",       step_type=StepType.FUNCTION, handler=generate_report,
                 dependencies=["regional_analysis", "product_analysis"]),
        ],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    random.seed(42)
    job = build_job()

    # --- Plan d'exécution ---------------------------------------------------
    plan = WorkflowEngine().get_execution_plan(job)
    print("Plan d'exécution")
    print(f"  Ordre séquentiel : {' → '.join(plan['execution_order'])}")
    print(f"  Chemin critique  : {' → '.join(plan['critical_path'][0])} ({plan['critical_path'][1]} step(s))")
    print("  Groupes parallèles :")
    for i, group in enumerate(plan["parallel_groups"], 1):
        marker = "(parallèle)" if len(group) > 1 else ""
        print(f"    Groupe {i}: {', '.join(group)} {marker}")

    # --- Exécution séquentielle (comportement par défaut) -------------------
    print("\n--- Exécution SÉQUENTIELLE (WorkflowEngine()) ---")
    t0 = time.perf_counter()
    result_seq = WorkflowEngine().run(job)
    dur_seq = time.perf_counter() - t0
    print(f"  Statut : {result_seq.status.value}  |  Durée : {dur_seq:.2f}s")

    # --- Exécution parallèle (ParallelRunner) --------------------------------
    print("\n--- Exécution PARALLÈLE (WorkflowEngine(parallel=True)) ---")
    random.seed(42)  # même seed pour comparaison équitable
    t0 = time.perf_counter()
    result_par = WorkflowEngine(parallel=True).run(job)
    dur_par = time.perf_counter() - t0
    print(f"  Statut : {result_par.status.value}  |  Durée : {dur_par:.2f}s")

    # --- Comparaison --------------------------------------------------------
    if dur_seq > 0:
        gain = (dur_seq - dur_par) / dur_seq * 100
        print(f"\nGain parallèle : {gain:.0f}%  ({dur_seq:.2f}s → {dur_par:.2f}s)")

    # --- Résultats ----------------------------------------------------------
    report_run = next(s for s in result_par.step_runs if s.step_name == "final_report")
    if report_run.output_data:
        r = report_run.output_data
        print("\nRésultats :")
        print(f"  Meilleure région  : {r['top_region']['name']} ({r['top_region']['sales']:.0f} €)")
        print(f"  Meilleur produit  : {r['top_product']['name']} ({r['top_product']['sales']:.0f} €)")


if __name__ == "__main__":
    main()
