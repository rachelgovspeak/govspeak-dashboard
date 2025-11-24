# app.py
# GovSpeak HCP Federal Analytics Dashboard
# - Clients can upload multiple Excel files
# - Reads ALL sheets (tabs) from each file
# - Auto-maps your icotec-style columns (ICDDisplay, EncountersRedacted, CPTCountsRedacted, etc.)
# - Simple password protection

import streamlit as st
import pandas as pd
import plotly.express as px

# ---------------------------
# Page config
# ---------------------------

st.set_page_config(
    page_title="GovSpeak HCP Federal Analytics",
    layout="wide",
)

# ---------------------------
# Simple Authentication (hard-coded password)
# ---------------------------

DASHBOARD_PASSWORD = "test123"  # <- change this if you want a different password


def check_password():
    """Simple password gate."""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    # Already logged in?
    if st.session_state["authenticated"]:
        return True

    # Show login UI in the sidebar
    with st.sidebar:
        st.header("🔒 Login")
        pwd = st.text_input("Dashboard password", type="password")
        login = st.button("Sign in")

        if login:
            if pwd == DASHBOARD_PASSWORD:
                st.session_state["authenticated"] = True
                st.success("Logged in successfully.")
                return True
            else:
                st.error("Incorrect password. Please try again.")
        st.info("Enter the password provided by GovSpeak to access the dashboard.")

    return False


if not check_password():
    st.stop()

# ---------------------------
# Branding / Styling
# ---------------------------

GOVSPEAK_BLUE = "#002855"
GOVSPEAK_CYAN = "#00BFFF"

st.markdown(
    f"""
    <style>
    .gov-header {{
        background: linear-gradient(90deg, {GOVSPEAK_BLUE}, {GOVSPEAK_CYAN});
        padding: 1rem 2rem;
        border-radius: 0.75rem;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    .gov-header h1 {{
        margin: 0;
        font-size: 1.8rem;
        font-weight: 700;
    }}
    .gov-header p {{
        margin: 0.35rem 0 0;
        font-size: 0.95rem;
        opacity: 0.93;
    }}
    .block-container {{
        padding-top: 1rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="gov-header">
      <h1>GovSpeak HCP Federal Analytics Dashboard</h1>
      <p>Federal commercialization simplified — VISN, facilities, providers, diagnoses, and procedures in one view.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "Upload one or more Excel files to normalize VISN, facility, state/city, ICD-10, CPT, "
    "encounters, provider name, and provider specialty into a unified analytics layer."
)

# ---------------------------
# Canonical columns & synonyms (tuned to your files)
# ---------------------------

CANONICAL_COLS = {
    "visn": "VISN",
    "facility_name": "FacilityName",
    "state": "State",
    "city": "City",
    "icd10": "ICD10_Code",
    "cpt": "CPT_Code",
    "encounters": "Encounters",
    "provider_name": "ProviderName",
    "provider_specialty": "ProviderSpecialty",
}

# These are all lowercased matches
COLUMN_SYNONYMS = {
    "visn": ["visn", "visn_id", "visn number", "visn_num"],
    "facility_name": [
        "facility",
        "facility_name",
        "facility name",
        "station_name",
        "site_name",
        "hospitalname",
        "organizationname",
        "va facility",
    ],
    "state": ["state", "st"],
    "city": ["city", "town", "city_name"],
    "icd10": [
        "icd10",
        "icd_10",
        "icd-10",
        "dx_code",
        "diagnosis_code",
        "icddisplay",          # <-- your icotec column
    ],
    "cpt": ["cpt", "cpt_code", "cpt code", "procedure_code", "proc_code"],
    "encounters": [
        "encounters",
        "encounter_count",
        "visit_count",
        "visits",
        "total_encounters",
        "encountersredacted",  # <-- your icotec DX volume
        "cptcountsredacted",   # <-- your icotec CPT volume (for CPT chart)
    ],
    "provider_name": [
        "provider",
        "provider_name",
        "provider name",
        "providername",        # <-- your exact header
        "physician",
        "physician_name",
        "name",
        "hcp_name",
        "last name",
        "lastname",
    ],
    "provider_specialty": [
        "specialty",
        "provider_specialty",
        "provider specialty",
        "provclassandspecialization",  # <-- your icotec header
        "occ4",
        "occeng",
        "occupation",
    ],
}

# ---------------------------
# Helper functions
# ---------------------------

def standardize_columns(df: pd.DataFrame, manual_mapping: dict) -> pd.DataFrame:
    """
    Map messy client column names to standard names (CANONICAL_COLS).
    Priority:
      1) Manual mapping (user-selected)
      2) Automatic best-guess via synonyms
    """
    # 1) Manual mapping
    for canonical_key, canonical_name in CANONICAL_COLS.items():
        chosen = manual_mapping.get(canonical_key, "AUTO")
        if chosen not in (None, "AUTO"):
            if chosen in df.columns and chosen != canonical_name:
                df = df.rename(columns={chosen: canonical_name})

    # 2) Synonym-based auto mapping
    lower_to_original = {col.lower().strip(): col for col in df.columns}
    for canonical_key, synonyms in COLUMN_SYNONYMS.items():
        canonical_name = CANONICAL_COLS[canonical_key]

        # Already present?
        if canonical_name in df.columns:
            continue

        chosen = manual_mapping.get(canonical_key, "AUTO")
        if chosen not in (None, "AUTO"):
            # already handled above
            continue

        for synonym in synonyms:
            if synonym in lower_to_original:
                original_col = lower_to_original[synonym]
                df = df.rename(columns={original_col: canonical_name})
                break

    return df


def load_and_normalize(raw_dfs, manual_mapping: dict) -> pd.DataFrame:
    """
    Standardize columns across ALL sheets, concatenate, and clean.
    Each item in raw_dfs is a DataFrame from one sheet.
    """
    dfs = []
    for df in raw_dfs:
        clean = standardize_columns(df.copy(), manual_mapping)
        dfs.append(clean)

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)

    # Keep only the canonical columns that actually exist
    keep_cols = [v for v in CANONICAL_COLS.values() if v in combined.columns]
    if not keep_cols:
        return pd.DataFrame()

    combined = combined[keep_cols]

    # Cleanup strings
    for col in ["VISN", "FacilityName", "State", "City", "ICD10_Code", "CPT_Code",
                "ProviderName", "ProviderSpecialty"]:
        if col in combined.columns:
            combined[col] = combined[col].astype(str).str.strip()

    # Numeric encounters
    if "Encounters" in combined.columns:
        combined["Encounters"] = pd.to_numeric(combined["Encounters"], errors="coerce").fillna(0)

    combined = combined.drop_duplicates()
    return combined


def multiselect_filter(df, col_name, label):
    if col_name not in df.columns:
        return df
    options = sorted([x for x in df[col_name].dropna().unique() if x != "nan"])
    selected = st.sidebar.multiselect(label, options)
    if selected:
        df = df[df[col_name].isin(selected)]
    return df


# ---------------------------
# Sidebar – upload (reads ALL sheets)
# ---------------------------

st.sidebar.header("1. Upload Data")

uploaded_files = st.sidebar.file_uploader(
    "Upload one or more Excel files (.xlsx, .xls)",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("👆 Upload Excel files in the left sidebar to get started.")
    st.stop()

raw_dfs = []
all_columns = set()

for f in uploaded_files:
    try:
        # Read ALL sheets as a dict of DataFrames
        xls = pd.ExcelFile(f)
        for sheet_name in xls.sheet_names:
            df_sheet = xls.parse(sheet_name)
            # Keep track of where rows came from (optional debug)
            df_sheet["_source_file"] = f.name
            df_sheet["_source_sheet"] = sheet_name
            raw_dfs.append(df_sheet)
            all_columns.update(df_sheet.columns)
    except Exception as e:
        st.error(f"Error reading file `{f.name}`: {e}")

if not raw_dfs:
    st.warning("No sheets could be read from the uploaded files. Please check the format and try again.")
    st.stop()

all_columns = sorted(list(all_columns))

# ---------------------------
# Sidebar – Column Mapping UI
# ---------------------------

st.sidebar.header("2. Column Mapping (optional)")
st.sidebar.caption(
    "If your headers are non-standard, explicitly map them here. "
    "Otherwise, leave as 'Auto-detect' and GovSpeak will use best guesses."
)

def column_selector(canonical_key, label_hint):
    options = ["Auto-detect", "None"] + all_columns
    return st.sidebar.selectbox(
        label_hint,
        options=options,
        index=0,
        key=f"map_{canonical_key}",
    )

manual_mapping = {}
manual_mapping["visn"] = column_selector("visn", "VISN column")
manual_mapping["facility_name"] = column_selector("facility_name", "Facility column")
manual_mapping["state"] = column_selector("state", "State column")
manual_mapping["city"] = column_selector("city", "City column")
manual_mapping["icd10"] = column_selector("icd10", "ICD-10 column")
manual_mapping["cpt"] = column_selector("cpt", "CPT column")
manual_mapping["encounters"] = column_selector("encounters", "Encounters / Volume column")
manual_mapping["provider_name"] = column_selector("provider_name", "Provider Name column")
manual_mapping["provider_specialty"] = column_selector("provider_specialty", "Provider Specialty column")

# Normalize "Auto-detect" / "None"
for k, v in manual_mapping.items():
    if v == "Auto-detect":
        manual_mapping[k] = "AUTO"
    elif v == "None":
        manual_mapping[k] = None

# ---------------------------
# Normalize data
# ---------------------------

data = load_and_normalize(raw_dfs, manual_mapping)

if data.empty:
    st.warning(
        "No usable data found after normalization. "
        "Try adjusting the column mappings so VISN, Facility, ICD-10, CPT, Encounters, etc. are correctly mapped."
    )
    st.stop()

st.success(f"✅ Loaded and normalized {len(data):,} rows from {len(uploaded_files)} file(s).")

# ---------------------------
# Sidebar – Filters
# ---------------------------

st.sidebar.header("3. Filters")

filtered = data.copy()
filtered = multiselect_filter(filtered, "VISN", "VISN")
filtered = multiselect_filter(filtered, "FacilityName", "Facility")
filtered = multiselect_filter(filtered, "State", "State")
filtered = multiselect_filter(filtered, "City", "City")
filtered = multiselect_filter(filtered, "ProviderSpecialty", "Provider Specialty")
filtered = multiselect_filter(filtered, "ProviderName", "Provider Name")

if filtered.empty:
    st.warning("Filters removed all rows. Clear some filters to see data.")
    st.stop()

# ---------------------------
# Download Buttons
# ---------------------------

with st.expander("📥 Download normalized data"):
    st.write("Export the normalized GovSpeak dataset for offline analysis or to send back to stakeholders.")
    full_csv = data.to_csv(index=False).encode("utf-8")
    filt_csv = filtered.to_csv(index=False).encode("utf-8")

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "Download full normalized dataset (.csv)",
            data=full_csv,
            file_name="govspeak_normalized_all.csv",
            mime="text/csv",
        )
    with col_dl2:
        st.download_button(
            "Download filtered view (.csv)",
            data=filt_csv,
            file_name="govspeak_filtered_view.csv",
            mime="text/csv",
        )

# ---------------------------
# KPI Cards
# ---------------------------

st.subheader("Overview")

col1, col2, col3, col4 = st.columns(4)

with col1:
    total_encounters = int(filtered["Encounters"].sum()) if "Encounters" in filtered.columns else 0
    st.metric("Total Encounters / Volume", f"{total_encounters:,}")

with col2:
    distinct_providers = (
        filtered["ProviderName"].nunique() if "ProviderName" in filtered.columns else 0
    )
    st.metric("Distinct Providers", f"{distinct_providers:,}")

with col3:
    distinct_facilities = (
        filtered["FacilityName"].nunique() if "FacilityName" in filtered.columns else 0
    )
    st.metric("Distinct Facilities", f"{distinct_facilities:,}")

with col4:
    distinct_icd = filtered["ICD10_Code"].nunique() if "ICD10_Code" in filtered.columns else 0
    st.metric("Distinct ICD-10 Codes", f"{distinct_icd:,}")

st.markdown("---")

# ---------------------------
# Tabs for charts
# ---------------------------

tab1, tab2, tab3 = st.tabs([
    "By VISN & Facility",
    "By Diagnosis (ICD-10) & CPT",
    "By Provider & Specialty",
])

# Tab 1: VISN / Facility
with tab1:
    st.subheader("Encounters / Volume by VISN")
    if "VISN" in filtered.columns and "Encounters" in filtered.columns:
        visn_group = (
            filtered.groupby("VISN", as_index=False)["Encounters"]
            .sum()
            .sort_values("Encounters", ascending=False)
        )
        fig_visn = px.bar(
            visn_group,
            x="VISN",
            y="Encounters",
            title="Total Encounters / Volume by VISN",
            labels={"Encounters": "Encounters / Volume"},
        )
        fig_visn.update_layout(xaxis_title="VISN", yaxis_title="Encounters / Volume")
        st.plotly_chart(fig_visn, use_container_width=True)
    else:
        st.info("VISN or Encounters column not found (optional).")

    st.subheader("Top Facilities by Encounters / Volume")
    if "FacilityName" in filtered.columns and "Encounters" in filtered.columns:
        facility_group = (
            filtered.groupby("FacilityName", as_index=False)["Encounters"]
            .sum()
            .sort_values("Encounters", ascending=False)
            .head(25)
        )
        fig_fac = px.bar(
            facility_group,
            x="FacilityName",
            y="Encounters",
            title="Top Facilities by Encounters / Volume",
            labels={"FacilityName": "Facility", "Encounters": "Encounters / Volume"},
        )
        fig_fac.update_layout(
            xaxis_title="Facility",
            yaxis_title="Encounters / Volume",
            xaxis_tickangle=-45,
        )
        st.plotly_chart(fig_fac, use_container_width=True)
    else:
        st.info("FacilityName or Encounters column not found.")

# Tab 2: ICD-10 / CPT
with tab2:
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Top ICD-10 Codes by Encounters")
        if "ICD10_Code" in filtered.columns and "Encounters" in filtered.columns:
            icd_group = (
                filtered.groupby("ICD10_Code", as_index=False)["Encounters"]
                .sum()
                .sort_values("Encounters", ascending=False)
                .head(25)
            )
            fig_icd = px.bar(
                icd_group,
                x="ICD10_Code",
                y="Encounters",
                title="Top ICD-10 Codes (by Encounters)",
                labels={"ICD10_Code": "ICD-10 Code", "Encounters": "Encounters"},
            )
            fig_icd.update_layout(
                xaxis_title="ICD-10 Code",
                yaxis_title="Encounters",
                xaxis_tickangle=-45,
            )
            st.plotly_chart(fig_icd, use_container_width=True)
        else:
            st.info("ICD10_Code or Encounters column not found.")

    with col_right:
        st.subheader("Top CPT Codes by Volume")
        if "CPT_Code" in filtered.columns and "Encounters" in filtered.columns:
            cpt_group = (
                filtered.groupby("CPT_Code", as_index=False)["Encounters"]
                .sum()
                .sort_values("Encounters", ascending=False)
                .head(25)
            )
            fig_cpt = px.bar(
                cpt_group,
                x="CPT_Code",
                y="Encounters",
                title="Top CPT Codes (by Volume)",
                labels={"CPT_Code": "CPT Code", "Encounters": "Volume"},
            )
            fig_cpt.update_layout(
                xaxis_title="CPT Code",
                yaxis_title="Volume",
                xaxis_tickangle=-45,
            )
            st.plotly_chart(fig_cpt, use_container_width=True)
        else:
            st.info("CPT_Code or volume (Encounters) column not found.")

# Tab 3: Provider / Specialty
with tab3:
    st.subheader("Encounters / Volume by Provider Specialty")
    if "ProviderSpecialty" in filtered.columns and "Encounters" in filtered.columns:
        spec_group = (
            filtered.groupby("ProviderSpecialty", as_index=False)["Encounters"]
            .sum()
            .sort_values("Encounters", ascending=False)
            .head(25)
        )
        fig_spec = px.bar(
            spec_group,
            x="ProviderSpecialty",
            y="Encounters",
            title="Top Specialties (by Encounters / Volume)",
            labels={"ProviderSpecialty": "Provider Specialty", "Encounters": "Encounters / Volume"},
        )
        fig_spec.update_layout(
            xaxis_title="Provider Specialty",
            yaxis_title="Encounters / Volume",
            xaxis_tickangle=-45,
        )
        st.plotly_chart(fig_spec, use_container_width=True)
    else:
        st.info("ProviderSpecialty or Encounters column not found.")

    st.subheader("Top Providers by Encounters / Volume")
    if "ProviderName" in filtered.columns and "Encounters" in filtered.columns:
        provider_group = (
            filtered.groupby("ProviderName", as_index=False)["Encounters"]
            .sum()
            .sort_values("Encounters", ascending=False)
            .head(25)
        )
        fig_prov = px.bar(
            provider_group,
            x="ProviderName",
            y="Encounters",
            title="Top Providers (by Encounters / Volume)",
            labels={"ProviderName": "Provider", "Encounters": "Encounters / Volume"},
        )
        fig_prov.update_layout(
            xaxis_title="Provider",
            yaxis_title="Encounters / Volume",
            xaxis_tickangle=-45,
        )
        st.plotly_chart(fig_prov, use_container_width=True)
    else:
        st.info("ProviderName or Encounters column not found.")

# ---------------------------
# Raw data view
# ---------------------------

with st.expander("View normalized data table"):
    st.dataframe(filtered, use_container_width=True)

# Optional debug: show all columns we saw
with st.expander("Debug: columns detected across all sheets (you can ignore this for clients)"):
    st.write(sorted(all_columns))
