# 🔗 Network Link Tools Suite

A **Streamlit-based application** to analyze, validate, and clean up network link data.  
This tool is designed for **network administrators** who manage large-scale infrastructure and need to ensure database consistency between **Main DB** and **Phoenix DB**.

---

## ✨ Features

### 1. Link Analysis (Main DB vs Phoenix DB)
- Compare two network databases to identify **matching** and **missing** links.
- Automatically prioritize **Ethernet (Eth)** and **Aggregated Ethernet (AE)** ports when conflicts occur.
- Generate reports on:
  - 🔍 Missing Links
  - 🛠️ Port Corrections Needed

### 2. Duplicate Port Finder
- Detect duplicate port assignments across devices.
- Separate analysis for:
  - ⚡ **Source Ports**
  - 🎯 **Destination Ports**
- Export detailed reports in **CSV** format.

### 3. Remove Duplicate Links
- Clean up directional duplicates (**A→B vs B→A**).
- Prioritize **Eth/AE ports** when deciding which duplicate to keep.
- Generate a **summary of links** marked for removal.

---

## 📂 Required Input Format

Your input Excel/CSV must contain these columns:

| Column            | Description |
|-------------------|-------------|
| **Source**        | Device name (e.g., `Router1`, `SwitchA`) |
| **Source Port**   | Interface name (e.g., `GigabitEthernet0/0/1`, `ae10`) |
| **Destination**   | Connected device name |
| **Destination Port** | Interface name on the connected device |

✅ Column headers are automatically normalized (e.g., `src`, `source`, `Source` → **Source**).

---

## 🖥️ Usage

1. Run the Streamlit app:
   ```bash
   streamlit run app.py
