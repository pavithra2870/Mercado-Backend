import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import numpy as np
import os


def generate_visualizations(
    analysis_result: dict,
    job_id: str,
    output_dir: str = "./reports",
) -> list[str]:
    """
    Generates 3 data-derived charts.
    
    Expects analysis_result structure:
    {
      "risk": {
        "churn_events": [...],
        "timeline": [...],
        "estimated_monthly_price": 50.0
      },
      "competitor": {
        "competitor_name": "...",
        "metrics": [...],
        "our_scores": [...],
        "competitor_scores": [...]
      }
    }
    """
    os.makedirs(output_dir, exist_ok=True)
    charts = []
    plt.style.use("ggplot")

    #  Correctly extract from nested structure 
    risk_data       = analysis_result.get("risk", {})
    competitor_data = analysis_result.get("competitor", {})
    churn_events    = risk_data.get("churn_events", [])
    timeline        = risk_data.get("timeline", [])
    price           = risk_data.get("estimated_monthly_price", 50.0)

    # CHART 1: REVENUE RISK BAR
    if churn_events:
        try:
            df = pd.DataFrame(churn_events)

            # Guard: make sure required columns exist
            if "severity_score" not in df.columns or "category" not in df.columns:
                print("[Charts] churn_events missing required fields — skipping risk chart")
            else:
                df["loss"] = df["severity_score"].astype(float) * float(price)
                risk_sum = df.groupby("category")["loss"].sum().reset_index()
                risk_sum = risk_sum.sort_values("loss", ascending=True)

                fig, ax = plt.subplots(figsize=(8, 4))
                colors = plt.cm.Reds_r(np.linspace(0.3, 0.9, len(risk_sum)))
                bars = ax.barh(risk_sum["category"], risk_sum["loss"], color=colors)

                # Value labels on bars
                for bar, val in zip(bars, risk_sum["loss"]):
                    ax.text(
                        bar.get_width() + (risk_sum["loss"].max() * 0.01),
                        bar.get_y() + bar.get_height() / 2,
                        f"${val:,.0f}",
                        va="center", fontsize=9, color="#2c3e50"
                    )

                ax.set_title("ESTIMATED MONTHLY REVENUE AT RISK ($)", fontsize=10, fontweight="bold")
                ax.set_xlabel("Weighted Revenue Impact (USD)")
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                plt.tight_layout()

                path1 = os.path.join(output_dir, f"chart_risk_{job_id}.png")
                fig.savefig(path1, dpi=150, bbox_inches="tight")
                plt.close(fig)
                charts.append(path1)
                print(f"[Charts] Risk chart saved: {path1}")

        except Exception as e:
            print(f"[Charts] Risk chart failed: {e}")
            import traceback; traceback.print_exc()

    # CHART 2: INCIDENT TIMELINE 
    if timeline:
        try:
            df_t = pd.DataFrame(timeline)

            if "period" not in df_t.columns or "incident_count" not in df_t.columns:
                print("[Charts] timeline missing required fields — skipping")
            else:
                df_t["incident_count"] = df_t["incident_count"].astype(int)

                # Color bars by sentiment
                sentiment_colors = {
                    "Negative": "#e74c3c",
                    "Critical": "#c0392b",
                    "Neutral":  "#f39c12",
                    "Positive": "#27ae60",
                }
                bar_colors = [
                    sentiment_colors.get(s, "#95a5a6")
                    for s in df_t.get("sentiment", ["Neutral"] * len(df_t))
                ]

                fig, ax = plt.subplots(figsize=(9, 4))
                x = range(len(df_t))
                ax.bar(x, df_t["incident_count"], color=bar_colors, alpha=0.7, width=0.6)
                ax.plot(x, df_t["incident_count"], marker="o", color="#c0392b",
                        linewidth=2, zorder=5)
                ax.fill_between(x, df_t["incident_count"], alpha=0.08, color="#c0392b")

                ax.set_xticks(list(x))
                ax.set_xticklabels(df_t["period"].tolist(), rotation=20, ha="right", fontsize=9)
                ax.set_title("INCIDENT FREQUENCY TIMELINE", fontsize=10, fontweight="bold")
                ax.set_ylabel("Reported Issues")
                ax.grid(True, linestyle="--", alpha=0.4, axis="y")
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                plt.tight_layout()

                path2 = os.path.join(output_dir, f"chart_timeline_{job_id}.png")
                fig.savefig(path2, dpi=150, bbox_inches="tight")
                plt.close(fig)
                charts.append(path2)
                print(f"[Charts] Timeline chart saved: {path2}")

        except Exception as e:
            print(f"[Charts] Timeline chart failed: {e}")
            import traceback; traceback.print_exc()

    # CHART 3: COMPETITOR RADAR 
    if competitor_data and competitor_data.get("metrics"):
        try:
            categories  = competitor_data.get("metrics", [])
            our_scores  = competitor_data.get("our_scores", [])
            comp_scores = competitor_data.get("competitor_scores", [])
            comp_name   = competitor_data.get("competitor_name", "Competitor")

            if not (len(categories) == len(our_scores) == len(comp_scores)):
                print(f"[Charts] Radar: mismatched lengths — skipping")
            elif len(categories) < 3:
                print(f"[Charts] Radar: need at least 3 metrics — skipping")
            else:
                # Close the polygon loop
                cats  = [*categories, categories[0]]
                ours  = [*[float(s) for s in our_scores],  float(our_scores[0])]
                comps = [*[float(s) for s in comp_scores], float(comp_scores[0])]

                label_loc = np.linspace(0, 2 * np.pi, len(ours))

                fig = plt.figure(figsize=(7, 7))
                ax = fig.add_subplot(polar=True)

                ax.plot(label_loc, ours, label="Product", color="#2980b9", linewidth=2.5)
                ax.fill(label_loc, ours, color="#2980b9", alpha=0.15)

                ax.plot(label_loc, comps, label=comp_name, color="#e74c3c",
                        linewidth=2.5, linestyle="--")
                ax.fill(label_loc, comps, color="#e74c3c", alpha=0.08)

                ax.set_ylim(0, 10)
                ax.set_yticks([2, 4, 6, 8, 10])
                ax.set_yticklabels(["2", "4", "6", "8", "10"], fontsize=7, color="#95a5a6")
                ax.set_title(f"COMPETITIVE POSITIONING vs {comp_name}",
                             size=11, fontweight="bold", y=1.12)

                plt.thetagrids(np.degrees(label_loc[:-1]), labels=categories[:-1] + [categories[-1]])
                plt.legend(loc="upper right", bbox_to_anchor=(1.35, 1.15), fontsize=9)
                plt.tight_layout()

                path3 = os.path.join(output_dir, f"chart_radar_{job_id}.png")
                fig.savefig(path3, dpi=150, bbox_inches="tight")
                plt.close(fig)
                charts.append(path3)
                print(f"[Charts] Radar chart saved: {path3}")

        except Exception as e:
            print(f"[Charts] Radar chart failed: {e}")
            import traceback; traceback.print_exc()

    print(f"[Charts] Generated {len(charts)}/3 charts for job {job_id}")
    return charts