#!/usr/bin/env python3
"""
Multi-Bagger Research System - Streamlit UI

Single-file tabbed interface that calls ui_service exclusively.
No business logic in UI - only display, file upload, and service calls.

All actions require explicit as_of/date parameters for determinism.
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import streamlit as st
import pandas as pd
import json

# Import UI service (the ONLY imports from our codebase)
from multibagger.ui_service import (
    get_storage_policy,
    get_latest_snapshot,
    get_health_summary,
    list_stage_artifacts,
    run_monthly,
    run_daily,
    get_research_table,
    reconcile_portfolio,
    portfolio_show,
    monitor_daily,
    analytics_compute,
    ops_health,
    ops_rotate,
)
from multibagger.config import Config


# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="Multi-Bagger Research System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================================
# SIDEBAR - GLOBAL CONTROLS
# ============================================================================

def render_sidebar():
    """Render global controls and status in sidebar."""
    st.sidebar.title("🎯 Multi-Bagger Research")
    st.sidebar.markdown("---")

    # Global inputs
    st.sidebar.subheader("Global Settings")

    # Get latest snapshot for default
    latest = get_latest_snapshot()
    default_as_of = latest["as_of"] if latest["exists"] else datetime.now().strftime("%Y-%m")

    as_of = st.sidebar.text_input(
        "📅 As-of Month (YYYY-MM)",
        value=default_as_of,
        help="Month for pipeline operations"
    )

    check_date = st.sidebar.date_input(
        "📆 Check Date",
        value=date.today(),
        help="Date for monitoring/price checks"
    )

    output_dir = st.sidebar.text_input(
        "📁 Output Directory",
        value="snapshots",
        help="Directory for pipeline outputs"
    )

    dry_run = st.sidebar.checkbox(
        "🔍 Dry-Run Mode",
        value=False,
        help="Preview actions without executing"
    )

    st.sidebar.markdown("---")

    # Status panel
    st.sidebar.subheader("System Status")

    try:
        config = Config()

        # Database path
        db_path = Path("multibagger.db")
        db_exists = db_path.exists()
        st.sidebar.text(f"💾 DB: {'✅' if db_exists else '❌'} {db_path}")

        # Latest snapshot
        if latest["exists"]:
            st.sidebar.text(f"📂 Latest: ✅ {latest['as_of']}")
            st.sidebar.text(f"   {len(latest['stage_files'])} files")
        else:
            st.sidebar.text("📂 Latest: ❌ No snapshots")

        # Health status
        if latest["exists"]:
            health = get_health_summary(latest["as_of"])
            status_icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴", "UNKNOWN": "⚪"}
            st.sidebar.text(f"🏥 Health: {status_icon.get(health['status'], '⚪')} {health['status']}")

        # Data sources
        data_sources = config.get("data", {}).get("sources", {})
        enabled = [k for k, v in data_sources.items() if v.get("enabled", False)]
        st.sidebar.text(f"🔌 Sources: {', '.join(enabled) or 'None'}")

        # Storage policy
        policy = get_storage_policy()
        policy_icon = "🎯" if policy["persist_finalists_only"] else "💾"
        policy_status = "Finalists-only" if policy["persist_finalists_only"] else "All tickers"
        st.sidebar.text(f"{policy_icon} Storage: {policy_status}")

    except Exception as e:
        st.sidebar.error(f"Error loading config: {e}")

    return {
        "as_of": as_of,
        "check_date": check_date,
        "output_dir": output_dir,
        "dry_run": dry_run
    }


# ============================================================================
# TAB 1: DASHBOARD
# ============================================================================

def render_dashboard(globals_dict):
    """Render dashboard with latest run status and quick links."""
    st.header("📊 Dashboard")

    as_of = globals_dict["as_of"]

    # Latest snapshot info
    latest = get_latest_snapshot()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Latest Snapshot", latest["as_of"] if latest["exists"] else "None")

    with col2:
        health = get_health_summary(latest["as_of"]) if latest["exists"] else {"status": "UNKNOWN"}
        status_color = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴", "UNKNOWN": "⚪"}
        st.metric("Health Status", f"{status_color.get(health['status'], '⚪')} {health['status']}")

    with col3:
        artifact_count = len(latest["stage_files"]) if latest["exists"] else 0
        st.metric("Artifacts", artifact_count)

    st.markdown("---")

    # Stage artifacts
    if latest["exists"]:
        st.subheader(f"📂 Artifacts for {latest['as_of']}")

        artifacts = list_stage_artifacts(latest["as_of"])

        if artifacts:
            # Group by type
            csvs = [a for a in artifacts if a["type"] == "csv"]
            jsons = [a for a in artifacts if a["type"] == "json"]
            mds = [a for a in artifacts if a["type"] == "md"]

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**CSV Files**")
                for artifact in csvs[:5]:  # Top 5
                    size_kb = artifact["size_bytes"] / 1024
                    st.text(f"• {artifact['name']} ({size_kb:.1f} KB)")

            with col2:
                st.markdown("**JSON Files**")
                for artifact in jsons[:5]:
                    size_kb = artifact["size_bytes"] / 1024
                    st.text(f"• {artifact['name']} ({size_kb:.1f} KB)")

            with col3:
                st.markdown("**Reports (MD)**")
                for artifact in mds[:5]:
                    size_kb = artifact["size_bytes"] / 1024
                    st.text(f"• {artifact['name']} ({size_kb:.1f} KB)")

            # Download all artifacts button
            if st.button("📥 Download All Artifacts Info"):
                artifacts_df = pd.DataFrame(artifacts)
                st.download_button(
                    "Download CSV",
                    artifacts_df.to_csv(index=False),
                    file_name=f"artifacts_{latest['as_of']}.csv",
                    mime="text/csv"
                )
        else:
            st.info("No artifacts found for this snapshot.")
    else:
        st.warning("No snapshots found. Run the monthly pipeline first.")


# ============================================================================
# TAB 2: RUN PIPELINE
# ============================================================================

def render_run_pipeline(globals_dict):
    """Render pipeline execution controls."""
    st.header("🚀 Run Pipeline")

    as_of = globals_dict["as_of"]
    check_date = globals_dict["check_date"]
    output_dir = globals_dict["output_dir"]
    dry_run = globals_dict["dry_run"]

    # Mode selector
    mode = st.radio(
        "Select Mode",
        ["Monthly (Full Pipeline)", "Daily (Monitoring)"],
        horizontal=True
    )

    st.markdown("---")

    if mode == "Monthly (Full Pipeline)":
        st.subheader("🗓️ Monthly Pipeline")
        st.markdown("""
        Runs the full pipeline:
        1. Universe Build
        2. Screens (Fast → Quality → Business → Red Flags → Research)
        3. Portfolio Reconciliation
        4. Health Check
        """)

        if st.button("▶️ Run Monthly Pipeline", type="primary"):
            with st.spinner(f"Running monthly pipeline for {as_of}..."):
                result = run_monthly(as_of=as_of, output_dir=output_dir, dry_run=dry_run)

                if result["success"]:
                    st.success(f"✅ Monthly pipeline completed for {as_of}")

                    # Show metrics
                    with st.expander("📊 Metrics"):
                        st.json(result["metrics"])

                    # Show artifacts
                    if result["artifacts"]:
                        st.markdown(f"**Generated {len(result['artifacts'])} artifacts**")
                        for artifact in result["artifacts"][:10]:  # Show first 10
                            st.text(f"• {artifact}")
                else:
                    st.error(f"❌ Pipeline failed: {result['log']}")

                    # Show warnings
                    if result["warnings"]:
                        for warning in result["warnings"]:
                            st.warning(warning)

    else:  # Daily
        st.subheader("📅 Daily Monitoring")
        st.markdown("""
        Runs daily monitoring to check for:
        - Stop-loss breaches
        - Target price approaches
        - Thesis risks (new red flags)
        """)

        if st.button("▶️ Run Daily Monitoring", type="primary"):
            with st.spinner(f"Running daily monitoring for {check_date}..."):
                result = run_daily(check_date=check_date, as_of=as_of, dry_run=dry_run)

                if result["success"]:
                    st.success(f"✅ Daily monitoring completed for {check_date}")

                    # Show metrics
                    with st.expander("📊 Metrics"):
                        st.json(result["metrics"])

                    # Show artifacts
                    if result["artifacts"]:
                        st.markdown(f"**Generated {len(result['artifacts'])} artifacts**")
                        for artifact in result["artifacts"]:
                            st.text(f"• {artifact}")
                else:
                    st.error(f"❌ Monitoring failed: {result['log']}")

                    if result["warnings"]:
                        for warning in result["warnings"]:
                            st.warning(warning)


# ============================================================================
# TAB 3: RESEARCH
# ============================================================================

def render_research(globals_dict):
    """Render research results with filters."""
    st.header("🔬 Research Results")

    as_of = globals_dict["as_of"]

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        min_upside = st.number_input(
            "Min Upside %",
            min_value=0.0,
            max_value=1000.0,
            value=0.0,
            step=10.0
        )

    with col2:
        sector = st.selectbox("Sector", ["All"] + ["Technology", "Healthcare", "Finance", "Consumer", "Industrial"])

    with col3:
        red_flags_only = st.checkbox("Red Flags Passed Only", value=True)

    # Load research data
    filters = {
        "min_upside_pct": min_upside,
        "sector": sector,
        "red_flags_passed_only": red_flags_only
    }

    df, meta = get_research_table(as_of, filters)

    if meta["warnings"]:
        for warning in meta["warnings"]:
            st.warning(warning)

    if not df.empty:
        st.subheader(f"📊 {len(df)} Candidates")

        # Display table
        st.dataframe(df, use_container_width=True)

        # Download buttons
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "📥 Download CSV",
                df.to_csv(index=False),
                file_name=f"research_{as_of}.csv",
                mime="text/csv"
            )

        with col2:
            st.download_button(
                "📥 Download JSON",
                df.to_json(orient="records", indent=2),
                file_name=f"research_{as_of}.json",
                mime="application/json"
            )
    else:
        st.info(f"No research data found for {as_of}. Run the research stage first.")

    # Storage policy note
    st.markdown("---")
    policy = get_storage_policy()
    if policy["persist_finalists_only"]:
        st.info(
            "📊 **Storage Policy**: When a stock is confirmed in Top N during research, "
            "its heavy data (fundamentals & factors) is automatically promoted from staging "
            "to the canonical store. This promotion is idempotent and happens once per finalist."
        )


# ============================================================================
# TAB 4: PORTFOLIO
# ============================================================================

def render_portfolio(globals_dict):
    """Render portfolio reconciliation and saved portfolios."""
    st.header("💼 Portfolio Management")

    as_of = globals_dict["as_of"]

    # Sub-tabs
    subtab1, subtab2 = st.tabs(["Reconcile Holdings", "Show Saved Portfolio"])

    with subtab1:
        st.subheader("📊 Reconcile Holdings")

        st.markdown("""
        Upload your current holdings (CSV or JSON) to reconcile against model recommendations.
        """)

        # File uploader
        uploaded_file = st.file_uploader(
            "Upload Holdings File",
            type=["csv", "json"],
            help="CSV with columns: symbol, shares, entry_price"
        )

        if uploaded_file:
            # Save to temp file
            temp_path = Path("/tmp") / uploaded_file.name
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            st.success(f"✅ Uploaded {uploaded_file.name}")

            # Options
            col1, col2 = st.columns(2)
            with col1:
                persist = st.checkbox("💾 Persist to Database", value=False)
            with col2:
                top_n = st.number_input("Top N Candidates", min_value=5, max_value=50, value=15)

            if st.button("▶️ Run Reconciliation", type="primary"):
                with st.spinner("Reconciling portfolio..."):
                    result = reconcile_portfolio(
                        as_of=as_of,
                        holdings_file_path=str(temp_path),
                        persist=persist,
                        top_n=top_n
                    )

                    if result["warnings"]:
                        for warning in result["warnings"]:
                            st.warning(warning)

                    # Show actions
                    if not result["actions_df"].empty:
                        st.subheader("📋 Recommended Actions")
                        st.dataframe(result["actions_df"], use_container_width=True)

                        st.download_button(
                            "📥 Download Actions CSV",
                            result["actions_df"].to_csv(index=False),
                            file_name=f"actions_{as_of}.csv",
                            mime="text/csv"
                        )

                    # Show reconciliation
                    if not result["reconcile_df"].empty:
                        with st.expander("📊 Full Reconciliation"):
                            st.dataframe(result["reconcile_df"], use_container_width=True)

                    # Show metrics
                    if result["metrics"]:
                        with st.expander("📊 Metrics"):
                            st.json(result["metrics"])

    with subtab2:
        st.subheader("📂 Saved Portfolio")

        if st.button("🔄 Load Portfolio"):
            with st.spinner(f"Loading portfolio for {as_of}..."):
                result = portfolio_show(as_of)

                if result["warnings"]:
                    for warning in result["warnings"]:
                        st.warning(warning)

                # Show positions
                if not result["positions_df"].empty:
                    st.subheader("📊 Positions")
                    st.dataframe(result["positions_df"], use_container_width=True)

                    # Chart weights
                    if "weight_pct" in result["positions_df"].columns:
                        st.bar_chart(
                            result["positions_df"].set_index("symbol")["weight_pct"]
                        )

                # Show actions
                if not result["actions_df"].empty:
                    st.subheader("📋 Actions")
                    st.dataframe(result["actions_df"], use_container_width=True)

                # Show metrics
                if result["metrics"]:
                    with st.expander("📊 Metrics"):
                        st.json(result["metrics"])


# ============================================================================
# TAB 5: MONITORING
# ============================================================================

def render_monitoring(globals_dict):
    """Render daily monitoring results."""
    st.header("👁️ Daily Monitoring")

    as_of = globals_dict["as_of"]
    check_date = globals_dict["check_date"]
    dry_run = globals_dict["dry_run"]

    st.markdown(f"""
    Monitor portfolio positions for:
    - 🔴 **STOP_LOSS**: Price breached downside protection
    - 🟡 **NEAR_TARGET**: Price approaching fair value
    - 🟠 **THESIS_RISK**: New red flags or low upside
    """)

    if st.button("▶️ Run Monitoring", type="primary"):
        with st.spinner(f"Running monitoring for {check_date}..."):
            result = monitor_daily(check_date=check_date, as_of=as_of, dry_run=dry_run)

            if result["warnings"]:
                for warning in result["warnings"]:
                    st.warning(warning)

            # Show alerts
            if not result["alerts_df"].empty:
                st.subheader(f"🚨 {len(result['alerts_df'])} Alerts")

                # Color-code by signal
                def color_signal(val):
                    colors = {
                        "STOP_LOSS": "background-color: #ff4444",
                        "NEAR_TARGET": "background-color: #ffaa00",
                        "THESIS_RISK": "background-color: #ff8800"
                    }
                    return colors.get(val, "")

                styled_df = result["alerts_df"].style.applymap(color_signal, subset=["signal"])
                st.dataframe(styled_df, use_container_width=True)

                # Download
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "📥 Download CSV",
                        result["alerts_df"].to_csv(index=False),
                        file_name=f"alerts_{check_date}.csv",
                        mime="text/csv"
                    )

                with col2:
                    st.download_button(
                        "📥 Download JSON",
                        result["alerts_df"].to_json(orient="records", indent=2),
                        file_name=f"alerts_{check_date}.json",
                        mime="application/json"
                    )
            else:
                st.success("✅ No alerts for this date")

            # Show metrics
            if result["metrics"]:
                with st.expander("📊 Metrics"):
                    st.json(result["metrics"])


# ============================================================================
# TAB 6: ANALYTICS
# ============================================================================

def render_analytics(globals_dict):
    """Render performance analytics."""
    st.header("📈 Performance Analytics")

    as_of = globals_dict["as_of"]

    # Inputs
    col1, col2 = st.columns(2)

    with col1:
        window = st.number_input(
            "Lookback Window (months)",
            min_value=6,
            max_value=60,
            value=36,
            step=6
        )

    with col2:
        bench_symbols = st.text_input(
            "Benchmark Symbols",
            value="SPY",
            help="Comma-separated list"
        ).split(",")

    if st.button("▶️ Compute Analytics", type="primary"):
        with st.spinner("Computing analytics..."):
            result = analytics_compute(
                as_of=as_of,
                window=window,
                bench_symbols=[s.strip() for s in bench_symbols]
            )

            if result["warnings"]:
                for warning in result["warnings"]:
                    st.warning(warning)

            metrics = result["metrics_json"]

            if metrics and "error" not in metrics:
                # Summary metrics
                st.subheader("📊 Summary")

                col1, col2, col3, col4 = st.columns(4)

                returns = metrics.get("returns", {})
                risk = metrics.get("risk", {})

                with col1:
                    st.metric("Total Return", f"{returns.get('total_return_pct', 0):.2f}%")

                with col2:
                    st.metric("CAGR", f"{returns.get('cagr_pct', 0):.2f}%")

                with col3:
                    st.metric("Volatility", f"{returns.get('volatility_pct', 0):.2f}%")

                with col4:
                    st.metric("Max Drawdown", f"{risk.get('max_drawdown_pct', 0):.2f}%")

                # Risk metrics
                st.subheader("📉 Risk Metrics")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Sharpe Ratio", f"{returns.get('sharpe_ratio', 0):.2f}")

                with col2:
                    st.metric("Calmar Ratio", f"{returns.get('calmar_ratio', 0):.2f}")

                with col3:
                    st.metric("Recovery Time", f"{risk.get('recovery_months', 0)} months")

                # Benchmark comparison
                bench = metrics.get("benchmark_comparison")
                if bench:
                    st.subheader("📊 Benchmark Comparison")

                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.metric("Alpha", f"{bench.get('alpha_pct', 0):.2f}%")

                    with col2:
                        st.metric("Beta", f"{bench.get('beta', 0):.2f}")

                    with col3:
                        st.metric("R²", f"{bench.get('r_squared', 0):.2f}")

                    with col4:
                        st.metric("Info Ratio", f"{bench.get('information_ratio', 0):.2f}")

                # Attribution
                contrib_df = result["contrib_df"]
                if not contrib_df.empty:
                    st.subheader("🎯 Top Contributors")
                    st.dataframe(contrib_df, use_container_width=True)

                # Download
                if result["outputs"]:
                    st.markdown("---")
                    st.subheader("📥 Downloads")

                    for output_type, output_path in result["outputs"].items():
                        if Path(output_path).exists():
                            with open(output_path) as f:
                                content = f.read()

                            st.download_button(
                                f"Download {output_type.upper()}",
                                content,
                                file_name=Path(output_path).name
                            )
            else:
                st.error("No analytics data available. Ensure portfolio runs exist.")


# ============================================================================
# TAB 7: OPS & HEALTH
# ============================================================================

def render_ops_health(globals_dict):
    """Render ops and health checks."""
    st.header("⚙️ Operations & Health")

    as_of = globals_dict["as_of"]

    # Sub-tabs
    subtab1, subtab2 = st.tabs(["Health Checks", "Snapshot Rotation"])

    with subtab1:
        st.subheader("🏥 System Health")

        if st.button("▶️ Run Health Checks", type="primary"):
            with st.spinner("Running health checks..."):
                result = ops_health(as_of)

                if result["warnings"]:
                    for warning in result["warnings"]:
                        st.warning(warning)

                # Show status
                status_color = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴", "ERROR": "❌"}
                st.markdown(f"### Overall Status: {status_color.get(result['status'], '⚪')} {result['status']}")

                # Show checks
                if not result["checks_df"].empty:
                    st.dataframe(result["checks_df"], use_container_width=True)

                # Show detailed metrics
                if result["metrics_json"]:
                    with st.expander("📊 Detailed Metrics"):
                        st.json(result["metrics_json"])

                # Report path
                if result["report_path"]:
                    st.info(f"Report saved: {result['report_path']}")

    with subtab2:
        st.subheader("🗑️ Snapshot Rotation")

        st.warning("⚠️ This will delete old snapshot directories. Use with caution!")

        keep_months = st.number_input(
            "Keep Recent Months",
            min_value=1,
            max_value=36,
            value=12
        )

        execute = st.checkbox(
            "✅ Execute (Delete Files)",
            value=False,
            help="Check to actually delete. Default is dry-run."
        )

        if execute:
            st.error("⚠️ EXECUTE MODE ENABLED - Files will be deleted!")

        if st.button("▶️ Run Rotation", type="primary" if not execute else "secondary"):
            if execute:
                # Confirmation
                confirm = st.text_input("Type 'DELETE' to confirm:")
                if confirm != "DELETE":
                    st.error("Please type 'DELETE' to confirm execution.")
                    st.stop()

            with st.spinner("Running rotation..."):
                result = ops_rotate(keep_months=keep_months, execute=execute)

                if result["warnings"]:
                    for warning in result["warnings"]:
                        st.warning(warning)

                # Show preview
                if not result["preview_df"].empty:
                    st.subheader("📋 Rotation Preview")
                    st.dataframe(result["preview_df"], use_container_width=True)

                    # Summary
                    deleted_count = len([p for p in result["deleted_paths"]])
                    bytes_freed = result["bytes_freed"]
                    mb_freed = bytes_freed / (1024 * 1024)

                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Snapshots Deleted", deleted_count)
                    with col2:
                        st.metric("Space Freed", f"{mb_freed:.2f} MB")

                    if not execute:
                        st.info("🔍 Dry-run mode. No files were deleted. Check 'Execute' to delete.")
                    else:
                        st.success("✅ Files deleted successfully.")
                else:
                    st.info("No snapshots to delete.")


# ============================================================================
# MAIN APP
# ============================================================================

def main():
    """Main application entry point."""

    # Render sidebar and get global settings
    globals_dict = render_sidebar()

    # Main title
    st.title("📈 Multi-Bagger Research System")
    st.markdown("Systematic investment research pipeline with deterministic outputs")
    st.markdown("---")

    # Tab navigation
    tabs = st.tabs([
        "📊 Dashboard",
        "🚀 Run Pipeline",
        "🔬 Research",
        "💼 Portfolio",
        "👁️ Monitoring",
        "📈 Analytics",
        "⚙️ Ops & Health"
    ])

    with tabs[0]:
        render_dashboard(globals_dict)

    with tabs[1]:
        render_run_pipeline(globals_dict)

    with tabs[2]:
        render_research(globals_dict)

    with tabs[3]:
        render_portfolio(globals_dict)

    with tabs[4]:
        render_monitoring(globals_dict)

    with tabs[5]:
        render_analytics(globals_dict)

    with tabs[6]:
        render_ops_health(globals_dict)


if __name__ == "__main__":
    main()
