import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re

# ---------- Utility functions ----------
def extract_match_part(device_name):
    """Extract the relevant part of device name based on underscore rules"""
    if not isinstance(device_name, str):
        return str(device_name)
    
    parts = device_name.split('_')
    
    # If only one underscore, take everything after it
    if len(parts) == 2:
        return parts[1]
    # If multiple underscores, take everything after the second-to-last underscore
    elif len(parts) > 2:
        return '_'.join(parts[-2:])
    # If no underscores, use the full name
    else:
        return device_name

def normalize_link(source, destination):
    """Ensure consistent link representation (alphabetical order) with underscore processing"""
    src_match = extract_match_part(str(source).strip())
    dst_match = extract_match_part(str(destination).strip())
    return tuple(sorted([src_match, dst_match]))

def canonicalize_columns(df):
    """Standardize column names for Source/Destination and their ports"""
    rename_map = {}
    for c in df.columns:
        key = c.strip().lower().replace('_', ' ').replace('-', ' ')
        key = ' '.join(key.split())
        if key in ('source', 'src'):
            rename_map[c] = 'Source'
        elif key in ('source port', 'src port', 'sourceport', 'srcport'):
            rename_map[c] = 'Source Port'
        elif key in ('destination', 'dest'):
            rename_map[c] = 'Destination'
        elif key in ('destination port', 'dest port', 'destinationport', 'destport'):
            rename_map[c] = 'Destination Port'
    df = df.rename(columns=rename_map)
    df.rename(columns=lambda x: x.strip(), inplace=True)
    return df

def get_preferred_ports(df, source, destination):
    """Get ports with priority for Eth- and ae- prefixes (case-insensitive)"""
    filtered = df[(df['Source'] == source) & (df['Destination'] == destination)]
    if filtered.empty:
        filtered = df[(df['Source'] == destination) & (df['Destination'] == source)]
    if filtered.empty:
        return None, None

    # First preference: Eth ports
    eth_source = filtered[filtered['Source Port'].astype(str).str.lower().str.startswith('eth')]
    eth_dest = filtered[filtered['Destination Port'].astype(str).str.lower().str.startswith('eth')]
    
    # Second preference: AE ports
    if eth_source.empty:
        eth_source = filtered[filtered['Source Port'].astype(str).str.lower().str.startswith('ae')]
    if eth_dest.empty:
        eth_dest = filtered[filtered['Destination Port'].astype(str).str.lower().str.startswith('ae')]
    
    source_port = eth_source['Source Port'].iloc[0] if not eth_source.empty else filtered['Source Port'].iloc[0]
    dest_port = eth_dest['Destination Port'].iloc[0] if not eth_dest.empty else filtered['Destination Port'].iloc[0]
    
    return source_port, dest_port

def port_priority_score(port):
    """Assign priority score to ports (higher is better)"""
    if pd.isna(port):
        return 0
    port_str = str(port).lower()
    if port_str.startswith('eth'):
        return 3
    elif port_str.startswith('ae'):
        return 2
    else:
        return 1

def find_duplicate_ports(df):
    """Return only rows with duplicate Source+Port or Dest+Port"""
    df = df.copy()
    df['Source+Port'] = df['Source'].astype(str).str.strip() + "_" + df['Source Port'].astype(str).str.strip()
    df['Dest+Port'] = df['Destination'].astype(str).str.strip() + "_" + df['Destination Port'].astype(str).str.strip()

    source_counts = df['Source+Port'].value_counts()
    dest_counts = df['Dest+Port'].value_counts()

    df['Source Port Duplicate'] = df['Source+Port'].map(source_counts) > 1
    df['Destination Port Duplicate'] = df['Dest+Port'].map(dest_counts) > 1

    return df[df['Source Port Duplicate'] | df['Destination Port Duplicate']]

def remove_duplicate_links_with_priority(df):
    """Remove duplicates with priority for Eth/AE ports"""
    df = df.copy()
    df['Normalized'] = df.apply(lambda x: normalize_link(x['Source'], x['Destination']), axis=1)
    
    # Calculate priority score for each row
    df['Source Priority'] = df['Source Port'].apply(port_priority_score)
    df['Dest Priority'] = df['Destination Port'].apply(port_priority_score)
    df['Total Priority'] = df['Source Priority'] + df['Dest Priority']
    
    # Keep the row with highest priority for each normalized link
    df = df.sort_values('Total Priority', ascending=False)
    cleaned = df.drop_duplicates(subset=['Normalized'], keep='first')
    duplicates = df[df.duplicated(subset=['Normalized'], keep='first')]
    
    # Drop temporary columns
    cleaned = cleaned.drop(columns=['Normalized', 'Source Priority', 'Dest Priority', 'Total Priority'])
    duplicates = duplicates.drop(columns=['Normalized', 'Source Priority', 'Dest Priority', 'Total Priority'])
    
    return cleaned, duplicates

def df_to_csv_download(df):
    return df.to_csv(index=False).encode('utf-8')

def read_excel_any(source):
    """Read Excel from an UploadedFile or from raw bytes stored in session_state"""
    if source is None:
        return None
    if isinstance(source, bytes):
        return pd.read_excel(BytesIO(source)).convert_dtypes()
    # UploadedFile or file-like
    try:
        source.seek(0)  # in case it was read before
    except Exception:
        pass
    return pd.read_excel(source).convert_dtypes()

# ---------- Streamlit UI ----------
st.title("Network Link Manager")

# Add user manual/instructions expander
with st.expander("📖 User Manual & Instructions", expanded=False):
    st.markdown("""
    <style>
    .manual-section h2 {
        color: #4CAF50;
        font-size: 22px;
        margin-bottom: 10px;
    }
    .manual-section h3 {
        color: #2196F3;
        font-size: 18px;
        margin-top: 18px;
    }
    .badge {
        display: inline-block;
        padding: 3px 8px;
        margin: 2px;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 600;
        background-color: #263238;
        color: #A5D6A7;
        font-family: monospace;
    }
    ul li {
        margin: 6px 0;
    }
    </style>

    <div class="manual-section">
    
    ## 🚀 Network Link Manager
    
    This application helps **network administrators** analyze and manage network link data with clarity and precision.
    
    ### 📌 Required Columns
    - <span class="badge">Source</span> → Device name (e.g., <span class="badge">Router1</span>)
    - <span class="badge">Source Port</span> → Interface (e.g., <span class="badge">Eth1/1</span>, <span class="badge">ae10</span>)
    - <span class="badge">Destination</span> → Connected device
    - <span class="badge">Destination Port</span> → Connected interface
    
    ### 🛠️ Tool Functions
    
    **1. Link Analysis (Main DB vs Phoenix DB)**  
    🔹 Compare two network databases to identify matching/missing links  
    🔹 Prioritize <span class="badge">Eth</span>/<span class="badge">AE</span> ports when multiple options exist  
    🔹 Generate reports on **missing links** & **port corrections**  
    
    **2. Duplicate Port Finder**  
    🔹 Detect duplicate port assignments across devices  
    🔹 Separate check for <span class="badge">Source</span> & <span class="badge">Destination</span> ports  
    🔹 Export detailed reports (CSV)  
    
    **3. Remove Duplicate Links**  
    🔹 Clean directional duplicates (<span class="badge">A→B</span> vs <span class="badge">B→A</span>)  
    🔹 Prioritize <span class="badge">Eth</span>/<span class="badge">AE</span> ports to keep  
    🔹 View summary of links marked for removal  
    
    ### 💡 Usage Tips
    - Upload Excel files with the required columns  
    - Column headers auto-normalized (e.g., "src", "source", "Source" → <span class="badge">Source</span>)  
    - Always prioritizes <span class="badge">Eth</span> first, then <span class="badge">AE</span>  
    - Download results for further review and reporting  
    
    </div>
    """, unsafe_allow_html=True)

tab_main, tab_dup_ports, tab_remove_dup = st.tabs([
    "Link Analysis (Main vs Phoenix DB)",
    "Duplicate Port Finder (Phoenix DB)",
    "Remove Duplicate Links"
])

# --- Panel 1: Main Link Analysis ---
with tab_main:
    st.subheader("Upload Main & Match Databases")
    col1, col2 = st.columns(2)
    with col1:
        main_db = st.file_uploader("Main Database", type=['xlsx', 'xls'], key="main_db")
    with col2:
        match_db = st.file_uploader("Phoenix Database", type=['xlsx', 'xls'], key="match_db")

    # Persist Phoenix DB (as bytes) for other tabs to reuse automatically
    if match_db:
        try:
            st.session_state["phoenix_db_bytes"] = match_db.getvalue()
            st.caption("Phoenix DB stored for other tabs.")
        except Exception:
            # Fallback: read then re-save as bytes
            match_db.seek(0)
            b = match_db.read()
            st.session_state["phoenix_db_bytes"] = b
            st.caption("Phoenix DB stored for other tabs.")

    if main_db and match_db:
        try:
            main_df = canonicalize_columns(read_excel_any(main_db))
            match_df = canonicalize_columns(read_excel_any(match_db))

            required_cols = ['Source', 'Source Port', 'Destination', 'Destination Port']
            for df, name in [(main_df, "Main"), (match_df, "Match")]:
                missing = [c for c in required_cols if c not in df.columns]
                if missing:
                    st.error(f"{name} missing columns: {', '.join(missing)}")
                    st.stop()

            # Sort links
            main_df['Normalized'] = main_df.apply(lambda x: normalize_link(x['Source'], x['Destination']), axis=1)
            match_df['Normalized'] = match_df.apply(lambda x: normalize_link(x['Source'], x['Destination']), axis=1)
            main_df = main_df.sort_values(by=['Normalized']).reset_index(drop=True)
            match_df = match_df.sort_values(by=['Normalized']).reset_index(drop=True)

            all_links = set(main_df['Normalized'])
            match_links = set(match_df['Normalized'])

            analysis_results = []
            missing_results = []
            port_corrections = []

            # NEW PORT CORRECTION LOGIC: Find all port inconsistencies
            # Group the main_df by normalized link to find groups with multiple entries
            link_groups = main_df.groupby('Normalized')
            for norm_link, group in link_groups:
                # Check if this link has multiple rows (implying potential port inconsistencies)
                if len(group) > 1:
                    # Get all unique ports for this link
                    unique_src_ports = group['Source Port'].astype(str).str.strip().unique()
                    unique_dst_ports = group['Destination Port'].astype(str).str.strip().unique()
                    
                    # Find the preferred ports for this link (Eth/ae priority)
                    sample_row = group.iloc[0]
                    src, dst = sample_row['Source'], sample_row['Destination']
                    corr_src_port, corr_dst_port = get_preferred_ports(main_df, src, dst)
                    
                    # For each row in the group, check if its ports match the corrected ones
                    for _, row in group.iterrows():
                        orig_src = str(row['Source Port']).strip()
                        orig_dst = str(row['Destination Port']).strip()
                        corr_src = str(corr_src_port).strip() if corr_src_port else 'N/A'
                        corr_dst = str(corr_dst_port).strip() if corr_dst_port else 'N/A'
                        
                        if orig_src != corr_src or orig_dst != corr_dst:
                            port_corrections.append({
                                'Link Name': f"{src} to {dst}",
                                'Source': src,
                                'Original Source Port': orig_src,
                                'Corrected Source Port': corr_src,
                                'Destination': dst,
                                'Original Destination Port': orig_dst,
                                'Corrected Destination Port': corr_dst,
                                'Port Priority Applied': (
                                    corr_src.lower().startswith(('eth', 'ae')) or
                                    corr_dst.lower().startswith(('eth', 'ae'))
                                ),
                                'Issue': 'Port Mismatch'
                            })

            # Continue with the original analysis for missing links
            for norm_link in all_links:
                # Find all rows in main_df that match this normalized link
                main_subset = main_df[main_df['Normalized'] == norm_link]
                if main_subset.empty:
                    continue
                    
                # Get the original source and destination from the first row
                original = main_subset.iloc[0]
                src, dst = original['Source'], original['Destination']
                
                # Check if this normalized link exists in the match database
                exists = norm_link in match_links
                
                # Get the preferred ports for this link
                corr_src_port, corr_dst_port = get_preferred_ports(main_df, src, dst)

                analysis_results.append({
                    'Link Name': f"{src} to {dst}",
                    'Source': src,
                    'Original Source Port': original['Source Port'],
                    'Destination': dst,
                    'Original Destination Port': original['Destination Port'],
                    'Match Status': 'Found' if exists else 'Missing',
                    'Normalized Link': str(norm_link)  # For debugging
                })

                if not exists:
                    missing_results.append({
                        'Link Name': f"{src} to {dst}",
                        'Source': src,
                        'Corrected Source Port': corr_src_port,
                        'Destination': dst,
                        'Corrected Destination Port': corr_dst_port,
                        'Normalized Link': str(norm_link)  # For debugging
                    })

            analysis_df = pd.DataFrame(analysis_results)
            missing_df = pd.DataFrame(missing_results)
            ports_df = pd.DataFrame(port_corrections)

            st.success(f"Total links: {len(analysis_df)}, Missing: {len(missing_df)}, Port Corrections Needed: {len(ports_df)}")

            st.write("### Main Analysis")
            st.dataframe(analysis_df)
            st.download_button("Download Main Analysis CSV", df_to_csv_download(analysis_df), "main_analysis.csv", "text/csv")

            st.write("### Missing Links")
            if not missing_df.empty:
                st.dataframe(missing_df)
                st.download_button("Download Missing Links CSV", df_to_csv_download(missing_df), "missing_links.csv", "text/csv")
            else:
                st.info("No missing links found")

            st.write("### Port Corrections Needed")
            if not ports_df.empty:
                st.dataframe(ports_df)
                st.download_button("Download Port Corrections CSV", df_to_csv_download(ports_df), "port_corrections.csv", "text/csv")
            else:
                st.info("No port corrections needed")

        except Exception as e:
            st.error(f"Error: {e}")

# --- Panel 2: Duplicate Port Finder ---
with tab_dup_ports:
    st.subheader("Find Duplicate Ports in Phoenix DB")
    
    # Prefer Phoenix DB saved from Panel 1; else allow manual upload
    phoenix_bytes = st.session_state.get("phoenix_db_bytes", None)
    match_db_dup = None
    if not phoenix_bytes:
        match_db_dup = st.file_uploader("Upload Phoenix Database (Excel)", type=['xlsx', 'xls'], key="match_db_dup")

    if phoenix_bytes or match_db_dup:
        try:
            source = phoenix_bytes if phoenix_bytes else match_db_dup
            match_df = canonicalize_columns(read_excel_any(source))
            
            # Check required columns
            required_cols = ['Source', 'Source Port', 'Destination', 'Destination Port']
            missing = [c for c in required_cols if c not in match_df.columns]
            if missing:
                st.error(f"Missing columns: {', '.join(missing)}")
            else:
                # Find duplicate ports
                dup_df = find_duplicate_ports(match_df)
                
                if dup_df.empty:
                    st.success("✅ No duplicate ports found in the database")
                else:
                    st.warning(f"⚠️ Found {len(dup_df)} rows with duplicate ports")
                    
                    # Download button at the top for easy access
                    st.download_button(
                        "⬇️ Download Duplicate Ports CSV", 
                        df_to_csv_download(dup_df.drop(columns=['Source+Port', 'Dest+Port'], errors='ignore')), 
                        "duplicate_ports.csv", 
                        "text/csv",
                        key="dup_ports_download"
                    )
                    
                    # Create two tabs for source and destination duplicates
                    tab_source, tab_dest = st.tabs(["Source Port Duplicates", "Destination Port Duplicates"])
                    
                    with tab_source:
                        st.subheader("Source Port Duplicates")
                        source_dups = dup_df[dup_df['Source Port Duplicate']]
                        if not source_dups.empty:
                            # Group by device and port
                            for (device, port), group in source_dups.groupby(['Source', 'Source Port']):
                                st.markdown(f"""
                                #### 🚨 Duplicate Source Port
                                
                              
                                **Device:** `{device}`  
                                **Port:** `{port}`
                                """)
                                
                                st.markdown(f"**Used in {len(group)} links as SOURCE port:**")
                                for _, row in group.iterrows():
                                    st.markdown(f"""
                                    - → `{row['Destination']}`  
                                      **Destination Port:** `{row['Destination Port']}`  
                                      **Link ID:** `{row.get('Link ID', 'N/A')}`
                                    """)
                                st.markdown("---")
                        else:
                            st.info("No source port duplicates found")
                    
                    with tab_dest:
                        st.subheader("Destination Port Duplicates")
                        dest_dups = dup_df[dup_df['Destination Port Duplicate']]
                        if not dest_dups.empty:
                            # Group by device and port
                            for (device, port), group in dest_dups.groupby(['Destination', 'Destination Port']):
                                st.markdown(f"""
                                #### 🚨 Duplicate Destination Port
                                
                                **Link Name:** Multiple Devices to {device}  
                                **Device:** `{device}`  
                                **Port:** `{port}`
                                """)
                                
                                st.markdown(f"**Used in {len(group)} links as DESTINATION port:**")
                                for _, row in group.iterrows():
                                    st.markdown(f"""
                                    - ← `{row['Source']}`  
                                      **Source Port:** `{row['Source Port']}`  
                                      **Link ID:** `{row.get('Link ID', 'N/A')}`
                                    """)
                                st.markdown("---")
                        else:
                            st.info("No destination port duplicates found")
                    
                    # Show full table in expander
                    with st.expander("View All Duplicates in Table Format"):
                        st.dataframe(dup_df.drop(columns=['Source+Port', 'Dest+Port'], errors='ignore'))
                        
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
    else:
        st.info("ℹ️ Upload Phoenix DB in the first tab or here to check for duplicate ports")

# --- Panel 3: Remove Duplicate Links ---
with tab_remove_dup:
    st.subheader("Remove Directional Duplicate Links (Phoenix DB)")

    # Prefer Phoenix DB saved from Panel 1; else allow manual upload
    phoenix_bytes = st.session_state.get("phoenix_db_bytes", None)
    file_remove_dup = None
    if not phoenix_bytes:
        file_remove_dup = st.file_uploader("Upload Phoenix Database (Excel)", type=['xlsx', 'xls'], key="file_remove_dup")

    if phoenix_bytes or file_remove_dup:
        try:
            source = phoenix_bytes if phoenix_bytes else file_remove_dup
            df = canonicalize_columns(read_excel_any(source))
            required_cols = ['Source', 'Destination', 'Source Port', 'Destination Port']
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                st.error(f"Missing columns: {', '.join(missing)}")
            else:
                # Check if Link ID column exists, if not create a dummy one
                if 'Link ID' not in df.columns:
                    df['Link ID'] = "Row " + (df.index + 1).astype(str)
                
                # Remove duplicates with port priority
                cleaned_df, duplicates_df = remove_duplicate_links_with_priority(df)
                
                # Identify which would be kept during cleaning (first occurrence)
                df['Normalized'] = df.apply(lambda x: normalize_link(x['Source'], x['Destination']), axis=1)
                df['Is_Kept'] = ~df.duplicated(subset=['Normalized'], keep='first')
                
                # Prepare duplicate report showing ALL duplicates with keep marker
                all_duplicates = df[df.duplicated(subset=['Normalized'], keep=False)].copy()
                all_duplicates['Keep Status'] = all_duplicates.duplicated(
                    subset=['Normalized'], keep='first'
                ).map({True: "Duplicate (would be removed)", False: "Original (would be kept)"})
                
                # Group duplicates for summary view
                grouped_duplicates = all_duplicates.groupby('Normalized').agg({
                    'Source': 'first',
                    'Destination': 'first',
                    'Source Port': 'first',
                    'Destination Port': 'first',
                    'Link ID': lambda x: list(x),
                    'Keep Status': 'count'
                }).reset_index()
                
                # Create a clean summary table for display
                summary_data = []
                for _, row in grouped_duplicates.iterrows():
                    # Get all link IDs for this connection
                    all_link_ids = row['Link ID']
                    
                    # Determine which ones would be kept (highest priority)
                    link_rows = all_duplicates[all_duplicates['Normalized'] == row['Normalized']]
                    kept_row = link_rows[link_rows['Keep Status'] == "Original (would be kept)"].iloc[0]
                    kept_link_id = kept_row['Link ID']
                    
                    # Link IDs to be removed (all except the kept one)
                    to_be_removed = [lid for lid in all_link_ids if lid != kept_link_id]
                    
                    # Use "to" instead of arrow symbol in link name
                    summary_data.append({
                        'Link Name': f"{row['Source']} to {row['Destination']}",
                        'Link IDs': ', '.join(map(str, all_link_ids)),
                        'Source': row['Source'],
                        'Source Port': row['Source Port'],
                        'Destination': row['Destination'],
                        'Destination Port': row['Destination Port'],
                        'To Be Removed': ', '.join(map(str, to_be_removed)) if to_be_removed else 'None'
                    })
                
                summary_df = pd.DataFrame(summary_data)

                st.write(f"Original rows: {len(df)}, Unique links: {len(cleaned_df)}, Duplicate groups: {len(summary_df)}")

                # Display the summary table
                st.write("### Duplicate Links Summary")
                st.dataframe(summary_df)
                
                # Download button for summary
                st.download_button(
                    "Download Duplicate Links Summary CSV", 
                    df_to_csv_download(summary_df), 
                    "duplicate_links_summary.csv", 
                    "text/csv",
                    key="summary_download"
                )
                
                # Show detailed view in expander
                with st.expander("View Detailed Duplicate Information"):
                    # Create detailed view with all duplicates
                    detailed_data = []
                    for _, row in all_duplicates.iterrows():
                        detailed_data.append({
                            'Link Name': f"{row['Source']} to {row['Destination']}",
                            'Link ID': row['Link ID'],
                            'Source': row['Source'],
                            'Source Port': row['Source Port'],
                            'Destination': row['Destination'],
                            'Destination Port': row['Destination Port'],
                            'Status': row['Keep Status']
                        })
                    
                    detailed_df = pd.DataFrame(detailed_data)
                    st.dataframe(detailed_df)
                    
                    # Download button for detailed view
                    st.download_button(
                        "Download Detailed Duplicates CSV", 
                        df_to_csv_download(detailed_df), 
                        "detailed_duplicates.csv", 
                        "text/csv",
                        key="detailed_download"
                    )

                # Show cleaned data
                with st.expander("Show Cleaned Links (unique only)"):
                    st.dataframe(cleaned_df)
                    st.download_button(
                        "Download Cleaned Links CSV", 
                        df_to_csv_download(cleaned_df), 
                        "cleaned_links.csv", 
                        "text/csv",
                        key="cleaned_download"
                    )

        except Exception as e:
            st.error(f"Error: {e}")
    else:
        st.info("Upload Phoenix DB in the first tab or here to run this tool.")

# Add copyright information at the bottom
st.markdown("---")
st.markdown("<div style='text-align: center; font-size: 12px;'>© Md. Akib Hossain</div>", unsafe_allow_html=True)
