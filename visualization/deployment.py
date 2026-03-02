import os
import glob
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches

# --- CONFIGURATION ---
DATA_DIR = str(Path(__file__).resolve().parent.parent / "data" / "validation_output" / "ist_txt")
GAP_THRESHOLD_HOURS = 12  # If data is missing for >12h, show a gap in the bar

def load_all_metadata(data_dir):
    print("Scanning data... this may take a moment.")
    files = glob.glob(os.path.join(data_dir, "**", "*.txt"), recursive=True)
    
    if not files:
        print("No files found.")
        return pd.DataFrame()

    # We only need ID, Type, and Time columns
    col_names = ['ID', 'Type', 'Year', 'Month', 'Day', 'Hour', 'Minute']
    use_cols = [0, 1, 4, 5, 6, 7, 8]

    df_list = []
    for f in files:
        try:
            df = pd.read_csv(f, sep=r'\s+', names=col_names, usecols=use_cols, header=None, engine='python')
            df_list.append(df)
        except: pass

    if not df_list: return pd.DataFrame()

    full_df = pd.concat(df_list, ignore_index=True)
    
    # Create Datetime
    full_df['Datetime'] = pd.to_datetime(full_df[['Year', 'Month', 'Day', 'Hour', 'Minute']])
    
    # Drop temp cols
    full_df = full_df[['ID', 'Type', 'Datetime']].sort_values(['ID', 'Datetime'])
    
    return full_df

def calculate_segments(df_buoy):
    """
    Converts a list of timestamps into start/end segments.
    Breaks segment if gap > GAP_THRESHOLD_HOURS.
    """
    if df_buoy.empty: return []

    times = df_buoy['Datetime'].values
    # Calculate difference between consecutive points in hours
    diffs = np.diff(times).astype('timedelta64[h]').astype(int)
    
    # Find indices where the gap is too large
    break_indices = np.where(diffs > GAP_THRESHOLD_HOURS)[0]
    
    segments = []
    start_idx = 0
    
    # Add breaks
    for break_idx in break_indices:
        # Segment from start to the point before the break
        segments.append((times[start_idx], times[break_idx]))
        start_idx = break_idx + 1
        
    # Add final segment
    segments.append((times[start_idx], times[-1]))
    
    # Convert numpy datetime64 to python datetime for matplotlib
    # and calculate duration
    mpl_segments = []
    for start, end in segments:
        start_dt = pd.to_datetime(start)
        end_dt = pd.to_datetime(end)
        duration = end_dt - start_dt
        
        # If single point, give it 1 hour width so it's visible
        if duration.total_seconds() == 0:
            duration = pd.Timedelta(hours=1)
            
        mpl_segments.append((mdates.date2num(start_dt), duration.total_seconds() / 86400.0)) # Days
        
    return mpl_segments

def plot_timeline(df):
    if df.empty: return

    # 1. Organize Data
    # Get unique Buoy/Type pairs and their start date for sorting
    buoy_summary = df.groupby('ID').agg(
        Type=('Type', 'first'),
        Start=('Datetime', 'min')
    ).reset_index()

    # Sort by Type then Start Date (so they cascade nicely)
    buoy_summary = buoy_summary.sort_values(['Start'], ascending=[True])
    
    # 2. Setup Plot
    fig, ax = plt.subplots(figsize=(16, max(8, len(buoy_summary) * 0.25))) # Dynamic height
    
    # Define Colors
    type_colors = {
        'SIMBA': 'tab:blue',
        'SIMB3': 'tab:cyan',
        'SNOW': 'tab:orange',
        'METEO': 'tab:green',
        'OMB': 'tab:purple',
        'CALIB': 'tab:red',
        'SVP': 'tab:pink'
    }

    # 3. Plot Bars
    y_ticks = []
    y_labels = []

    print("Calculating timeline segments...")
    
    for i, row in enumerate(buoy_summary.itertuples()):
        bid = row.ID
        btype = row.Type.strip() # Remove padding spaces
        
        # Get timestamps for this buoy
        sub_df = df[df['ID'] == bid]
        
        # Calculate segments (broken bars)
        segments = calculate_segments(sub_df)
        
        # Color fallback
        color = type_colors.get(btype, 'gray')
        
        # Plot broken bar (x_start, width)
        ax.broken_barh(segments, (i - 0.4, 0.8), facecolors=color, edgecolor='none')
        
        y_ticks.append(i)
        y_labels.append(f"{bid}")

    # 4. Formatting
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels, fontsize=9, fontfamily='monospace')
    ax.set_ylim(-1, len(y_ticks))
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=45)
    
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)
    ax.set_xlabel("Date")
    ax.set_title(f"Buoy Data Availability (Gap Threshold: {GAP_THRESHOLD_HOURS}h)")

    # 5. Custom Legend
    legend_patches = [mpatches.Patch(color=c, label=t) for t, c in type_colors.items()]
    ax.legend(handles=legend_patches, loc='upper left', bbox_to_anchor=(1, 1), title="Buoy Type")

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    df = load_all_metadata(DATA_DIR)
    plot_timeline(df)