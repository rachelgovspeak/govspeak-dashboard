import os
from typing import Dict, List, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st

# ------------------------------------------------------------------
# Page config
# ------------------------------------------------------------------
st.set_page_config(
    page_title="GovSpeak HCP Federal Analytics",
    layout="wide",
)

# ------------------------------------------------------------------
# Simple Authentication
# ------------------------------------------------------------------
ENV_PASSWORD = os.getenv("GOVSPEAK_DASH_PASSWORD")
DEFAULT_PASSWORD = "ChangeMe123!"  # change this if you don't use ENV_PASSWORD
DASHBOARD_PASSWORD = ENV_PASSWORD if ENV_PASSWORD else DEFAULT_PASSWORD


def check_password() -> bool:
    """Simple password gate using Streamlit session_state."""
    def password_entered():
        if st.session_state.get("password") == DASHBOARD_PASSWORD:
            st.session_state["authenticated"] = True
            # clear the password so it's not stored in plain text
            st.session_state["password"] = ""
        else:
            st.session_state["authenticated"] = False

    # If already authenticated, no need to show the password box again
    if st.session_state.get("authenticated"):
        return True

    st.title("GovSpeak HCP Federal Analytics")
    st.write("Please enter the dashboard password to continue.")
    st.text_input(
        "Password",
        type="password",
        key="password",
        on_change=password_entered,
    )

    if st.session_state.get("authenticated") is False:
        st.error("❌ Incorrect password. Please try again.")

    return False


# ------------------------------------------------------------------
# Sidebar drill-down filters (Facility → Specialty → ICD → Provider)
#   with *search* and *exact ICD list* support
# ------------------------------------------------------------------
def build_filters(
    base_df: pd.DataFrame,
    facility_col: str = "Facility",
    specialty_col: str = "ProvClassAndSpecialization",
    icd_col: str = "ICDDisplay",
    provider_col: str = "ProviderName",
) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    """
    Build chained sidebar filters and return the filtered dataframe
    plus the selected values.

    Adds:
    - Free-text search for ICD-10 (substring)
    - Exact ICD-10 list (comma-separated)
    - Free-text search for provider specialty (substring)
    """

    df = base_df.copy()
    filter_state: Dict[str, List[str]] = {}

    st.sidebar.header("🔍 Drill-down filters")

    # ---------------- Facility ----------------
    if facility_col in df.columns:
        facility_options = sorted(df[facility_col].dropna().unique())
        selected_facilities = st.sidebar.multiselect(
            "Facility",
            options=facility_options,
            default=facility_options,
        )
        if selected_facilities:
            df = df[df[facility_col].isin(selected_facilities)]
        filter_state["Facility"] = selected_facilities
    else:
        filter_state["Facility"] = []

    # ---------------- Provider Specialty search + multiselect ----------------
    if specialty_col in df.columns:
        st.sidebar.markdown("---")
        st.sidebar.subheader("🩺 Provider Specialty")

        # 1) Free-text specialty search (substring)
        spec_search = st.sidebar.text_input(
            "Search specialty (contains)",
            placeholder="e.g., Oncology, Radiology",
        )

        df_spec = df
        if spec_search:
            df_spec = df_spec[
                df_spec[specialty_col]
                .astype(str)
                .str.contains(spec_search, case=False, na=False)
            ]

        spec_options = sorted(df_spec[specialty_col].dropna().unique())
        selected_specs = st.sidebar.multiselect(
            "Provider Class / Specialization",
            options=spec_options,
            default=spec_options,
        )
        if selected_specs:
            df = df[df[specialty_col].isin(selected_specs)]

        filter_state["ProvClassAndSpecialization"] = selected_specs
        filter_state["ProvClassAndSpecialization_search"] = [spec_search] if spec_search else []
    else:
        filter_state["ProvClassAndSpecialization"] = []
        filter_state["ProvClassAndSpecialization_search"] = []

    # ---------------- ICD-10 search + exact list + multiselect ----------------
    if icd_col in df.columns:
        st.sidebar.markdown("---")
        st.sidebar.subheader("🧪 ICD-10 Codes")

        # 1) Exact list of ICD-10 codes (comma-separated)
        icd_exact_input = st.sidebar.text_input(
            "ICD-10 codes (comma separated)",
            placeholder="e.g., C50.911, C50.912",
        )

        if icd_exact_input.strip():
            exact_codes = [
                c.strip()
                for c in icd_exact_input.split(",")
                if c.strip()
            ]
            if exact_codes:
                df = df[df[icd_col].astype(str).isin(exact_codes)]
                filter_state["ICD_exact"] = exact_codes
        else:
            filter_state["ICD_exact"] = []

        # 2) Free-text ICD search (substring, e.g., 'C50', 'BREAST')
        icd_search = st.sidebar.text_input(
            "Search ICD (contains code or text)",
            placeholder="e.g., C50, pneumonia, fracture",
        )

        df_icd = df
        if icd_search:
            df_icd = df_icd[
                df_icd[icd_col]
                .astype(str)
                .str.contains(icd_search, case=False, na=False)
            ]

        # 3) Multiselect from the (possibly narrowed) list
        icd_options = sorted(df_icd[icd_col].dropna().unique())
        selected_icd = st.sidebar.multiselect(
            "ICD (Display)",
            options=icd_options,
            default=icd_options,
        )
        if selected_icd:
            df = df[df[icd_col].isin(selected_icd)]

        filter_state["ICDDisplay"] = selected_icd
        filter_state["ICD_search"] = [icd_search] if icd_search else []
    else:
        filter_state["ICDDisplay"] = []
        filter_state["ICD_search"] = []
        filter_state["ICD_exact"] = []

    # ---------------- Provider ----------------
    if provider_col in df.columns:
        st.sidebar.markdown("---")
        provider_options = sorted(df[provider_col].dropna().unique())
        selected_providers = st.sidebar.multiselect(
            "Provider",
            options=provider_options,
            default=provider_options,
        )
        if selected_providers:
            df = df[df[provider_col].isin(selected_providers)]
        filter_state["ProviderName"] = selected_providers
    else:
        filter_state["ProviderName"] = []

    return df, filter_state


# ------------------------------------------------------------------
# Unique-patient summary (per provider)
# ------------------------------------------------------------------
def build_provider_unique_patient_summary(
    df: pd.DataFrame,
    provider_col: str = "ProviderName",
    unique_patients_col: str = "UniquePatientsRedacted",
) -> pd.DataFrame:
    """
    Return one row per provider with a unique-patient count using the
    pre-aggregated UniquePatientsRedacted column.
    """
    if provider_col not in df.columns or unique_patients_col not in df.columns:
        return pd.DataFrame()

    dfn = df.copy()
    dfn[unique_patients_col] = pd.to_numeric(
        dfn[unique_patients_col], errors="coerce"
    ).fillna(0)

    summary = (
        dfn.groupby(provider_col)[unique_patients_col]
        .sum()
        .reset_index()
        .rename(columns={unique_patients_col: "Total_Unique_Patients"})
    )

    return summary


# ------------------------------------------------------------------
# Unique-patient slider filter (applies *after* drill-downs)
# ------------------------------------------------------------------
def apply_unique_patient_slider_filter(
    filtered_df: pd.DataFrame,
    provider_col: str = "ProviderName",
    unique_patients_col: str = "UniquePatientsRedacted",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Build a unique-patient summary per provider from the
    UniquePatientsRedacted column, add a sidebar slider
    to filter by total unique patients, and return:

        encounter_level_df_filtered,
        provider_unique,               # full provider summary
        provider_unique_filtered       # after slider
    """
    provider_unique = build_provider_unique_patient_summary(
        filtered_df,
        provider_col=provider_col,
        unique_patients_col=unique_patients_col,
    )

    if provider_unique.empty:
        return filtered_df, provider_unique, provider_unique

    min_up = int(provider_unique["Total_Unique_Patients"].min())
    max_up = int(provider_unique["Total_Unique_Patients"].max())
    default_range = (min_up, max_up)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🧬 Unique patient filter")

    up_min, up_max = st.sidebar.slider(
        "Filter providers by total unique patients (within current filters)",
        min_value=min_up,
        max_value=max_up,
        value=default_range,
        step=1,
    )

    provider_unique_filtered = provider_unique[
        provider_unique["Total_Unique_Patients"].between(up_min, up_max)
    ]

    # Use allowed providers to further filter underlying data
    allowed_providers = provider_unique_filtered[provider_col].unique()
    encounter_level_df_filtered = filtered_df[
        filtered_df[provider_col].isin(allowed_providers)
    ]

    return encounter_level_df_filtered, provider_unique, provider_unique_filtered


# ------------------------------------------------------------------
# Chart: Unique patients by provider
# ------------------------------------------------------------------
def render_unique_patients_chart(
    provider_unique_filtered: pd.DataFrame,
    provider_col: str = "ProviderName",
):
    """Bar chart + table for unique patients per provider."""
    st.markdown("### 👨‍⚕️ Unique Patients by Provider (current filters)")

    if provider_unique_filtered.empty:
        st.info("No data for the current filter combination.")
        return

    sort_col = "Total_Unique_Patients"
    df_plot = provider_unique_filtered.sort_values(sort_col, ascending=False)

    fig = px.bar(
        df_plot,
        x=provider_col,
        y=sort_col,
        title="Unique Patients per Provider",
    )
    fig.update_layout(
        xaxis_title="Provider",
        yaxis_title="Unique Patients",
        xaxis_tickangle=-45,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        df_plot,
        use_container_width=True,
        hide_index=True,
    )


# ------------------------------------------------------------------
# Data loading (supports MULTIPLE files)
# ------------------------------------------------------------------
def load_data(uploaded_files) -> pd.DataFrame:
    """
    Load provider-level data from one or more uploaded CSV or Excel files.
    Expected columns (at minimum):
        Facility, ProviderName, UniquePatientsRedacted, EncountersRedacted
    Optional:
        ProvClassAndSpecialization, ICDDisplay
    """
    if not uploaded_files:
        return pd.DataFrame()

    # If single file is passed, wrap in list for consistent handling
    if not isinstance(uploaded_files, list):
        uploaded_files = [uploaded_files]

    frames = []
    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name.lower()
        if file_name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            # default to Excel for .xlsx / .xls
            df = pd.read_excel(uploaded_file)
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    df_all = pd.concat(frames, ignore_index=True)

    return df_all


# ------------------------------------------------------------------
# Main dashboard logic
# ------------------------------------------------------------------
def run_dashboard(data: pd.DataFrame):
    """
    Call this after you have loaded your provider-level data.
    Required cols:
        Facility, ProviderName, UniquePatientsRedacted, EncountersRedacted
    Optional:
        ProvClassAndSpecialization, ICDDisplay
    """
    if data.empty:
        st.info("👋 Upload one or more provider-level CSV or Excel files to get started.")
        return

    required_cols = [
        "Facility",
        "ProviderName",
        "UniquePatientsRedacted",
        "EncountersRedacted",
    ]
    missing = [c for c in required_cols if c not in data.columns]
    if missing:
        st.error(
            "Your file is missing required columns: "
            + ", ".join(missing)
            + ". Please upload a file with at least these columns."
        )
        st.write("Available columns:", list(data.columns))
        return

    # Ensure numeric metrics
    data = data.copy()
    data["UniquePatientsRedacted"] = pd.to_numeric(
        data["UniquePatientsRedacted"], errors="coerce"
    ).fillna(0)
    data["EncountersRedacted"] = pd.to_numeric(
        data["EncountersRedacted"], errors="coerce"
    ).fillna(0)

    st.markdown("## GovSpeak HCP Federal Analytics")
    st.caption(
        "Drill down by Facility, Provider Class/Specialization, ICD Display, and Provider "
        "while filtering by unique patient counts."
    )

    # 1) Sidebar drill-down filters (with ICD & specialty search)
    filtered_df, filter_state = build_filters(
        data,
        facility_col="Facility",
        specialty_col="ProvClassAndSpecialization",
        icd_col="ICDDisplay",
        provider_col="ProviderName",
    )

    # 2) Unique-patient slider filter (further filters providers)
    filtered_df, provider_unique, provider_unique_filtered = (
        apply_unique_patient_slider_filter(
            filtered_df,
            provider_col="ProviderName",
            unique_patients_col="UniquePatientsRedacted",
        )
    )

    # ---------------- Top-level KPIs ----------------
    st.markdown("### 📊 Key Metrics (current filters)")
    col1, col2, col3 = st.columns(3)

    with col1:
        total_unique_patients = int(filtered_df["UniquePatientsRedacted"].sum())
        st.metric("Unique Patients (sum of redacted)", value=f"{total_unique_patients:,}")
    with col2:
        total_encounters = int(filtered_df["EncountersRedacted"].sum())
        st.metric("Total Encounters (redacted)", value=f"{total_encounters:,}")
    with col3:
        st.metric(
            "Active Providers",
            value=f"{filtered_df['ProviderName'].nunique():,}",
        )

    st.markdown("---")

    # ---------------- Facility-level bar chart ----------------
    if "Facility" in filtered_df.columns:
        st.markdown("### 🏨 Top Facilities by Unique Patients (current filters)")
        facility_agg = (
            filtered_df.groupby("Facility")["UniquePatientsRedacted"]
            .sum()
            .reset_index()
            .rename(columns={"UniquePatientsRedacted": "Unique_Patients_Redacted"})
        )

        facility_agg = facility_agg.sort_values(
            "Unique_Patients_Redacted", ascending=False
        )

        fig_facility = px.bar(
            facility_agg.head(25),
            x="Facility",
            y="Unique_Patients_Redacted",
            title="Top Facilities by Unique Patients (Redacted)",
        )
        fig_facility.update_layout(
            xaxis_title="Facility",
            yaxis_title="Unique Patients (Redacted)",
            xaxis_tickangle=-45,
        )
        st.plotly_chart(fig_facility, use_container_width=True)

    st.markdown("---")

    # ---------------- Unique patients by provider chart ----------------
    render_unique_patients_chart(
        provider_unique_filtered,
        provider_col="ProviderName",
    )

    # ---------------- Raw data preview ----------------
    with st.expander("🔎 View filtered provider-level data"):
        st.dataframe(
            filtered_df,
            use_container_width=True,
            hide_index=True,
        )


# ------------------------------------------------------------------
# Streamlit entrypoint
# ------------------------------------------------------------------
def main():
    # Password gate
    if not check_password():
        return

    st.sidebar.title("⚙️ Controls")
    st.sidebar.info(
        "Upload one or more provider-level Excel or CSV files with at least:\n\n"
        "- Facility\n- ProviderName\n- UniquePatientsRedacted\n- EncountersRedacted\n\n"
        "Optional columns:\n\n"
        "- ProvClassAndSpecialization\n- ICDDisplay\n\n"
        "Use the sidebar to drill down by facility, specialty, ICD-10 codes, provider, "
        "and unique patient ranges."
    )

    uploaded_files = st.file_uploader(
        "Upload provider-level file(s)",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )

    data = load_data(uploaded_files)
    run_dashboard(data)


if __name__ == "__main__":
    main()
