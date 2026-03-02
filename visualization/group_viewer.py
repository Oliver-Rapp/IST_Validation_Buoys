import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button, Slider
from collections import defaultdict, deque
from pathlib import Path
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import warnings

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
_DEFAULT_DATA_DIR = str(Path(__file__).resolve().parent.parent / "data" / "validation_output" / "ist_txt")
DATA_DIR = Path(os.environ.get("BUOY_VALIDATION_DIR", _DEFAULT_DATA_DIR))
MAX_DIST_KM = 30.0  # Max distance to consider buoys part of the same "camp"

class GroupValidationViewer:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.buoy_data = {} 
        self.groups = []
        self.current_idx = 0
        self.colors = plt.cm.tab10.colors
        
        self.ax_map = None
        self.ax_air = None
        self.ax_skin = None
        self.ax_press = None
        
        print("1. Loading all buoy data...")
        self.load_data()
        
        if not self.buoy_data:
            print(f"No data found in {self.data_dir}!")
            return

        print("2. Identifying groups/camps...")
        self.find_groups()
        
        if not self.groups:
            print("No multi-buoy groups found. Try increasing MAX_DIST_KM.")
            return

        print(f"3. Found {len(self.groups)} groups. Launching viewer...")
        self.setup_plot()
        self.update_plot()
        plt.show()

    def load_data(self):
        files = list(self.data_dir.rglob("*.txt"))
        if not files:
            return

        col_names = [
            'ID', 'Type', 'Lat', 'Lon', 'Year', 'Month', 'Day', 'Hour', 'Minute', 
            'Ts', 'T2m', 'Td', 'Press', 'FF', 'DD', 'Cloud', 'Ts_Qual', 'T2m_Qual'
        ]

        df_list = []
        for f in files:
            try:
                df = pd.read_csv(
                    f, 
                    delim_whitespace=True, 
                    names=col_names, 
                    header=None, 
                    dtype={'ID': str}
                )
                if not df.empty: 
                    df_list.append(df)
            except Exception as e:
                print(f"Error loading {f.name}: {e}")

        if not df_list:
            return

        # Combine all files into one DataFrame for bulk vectorized processing
        full_df = pd.concat(df_list, ignore_index=True)
        
        # Create Datetime index
        full_df['Datetime'] = pd.to_datetime(full_df[['Year', 'Month', 'Day', 'Hour', 'Minute']])
        
        # Conversions & Cleaning
        full_df['Ts_C'] = np.where(full_df['Ts'] > 100, full_df['Ts'] - 273.15, np.nan)
        full_df['T2m_C'] = np.where(full_df['T2m'] > 100, full_df['T2m'] - 273.15, np.nan)
        full_df['Press_hPa'] = np.where(full_df['Press'] > 800, full_df['Press'], np.nan)
        
        # Filter bad GPS
        full_df = full_df[(full_df['Lat'] != 0) & (full_df['Lon'] != 0)].dropna(subset=['Lat', 'Lon'])
        
        # Group by ID and store
        for bid, group in full_df.groupby('ID'):
            # Sort and set index, dropping duplicates in case of file overlap
            clean_group = group.sort_values('Datetime').drop_duplicates('Datetime').set_index('Datetime')
            self.buoy_data[bid] = clean_group

    def haversine(self, lat1, lon1, lat2, lon2):
        R = 6371.0
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        return R * 2 * np.arcsin(np.sqrt(a))

    def find_groups(self):
        """Finds buoys that were close to each other on the same day."""
        if not self.buoy_data: 
            return
        
        all_dfs = pd.concat(self.buoy_data.values())
        all_dfs['Date'] = all_dfs.index.date
        
        # Daily medians for robust proximity check
        daily = all_dfs.groupby(['ID', 'Date'])[['Lat', 'Lon']].median().reset_index()
        
        edges = set()
        for date, day_data in daily.groupby('Date'):
            buoys = day_data['ID'].tolist()
            lats = day_data['Lat'].tolist()
            lons = day_data['Lon'].tolist()
            n = len(buoys)
            
            for i in range(n):
                for j in range(i + 1, n):
                    if self.haversine(lats[i], lons[i], lats[j], lons[j]) <= MAX_DIST_KM:
                        edges.add(tuple(sorted([buoys[i], buoys[j]])))

        # BFS to find connected components
        adj = defaultdict(set)
        for b1, b2 in edges:
            adj[b1].add(b2)
            adj[b2].add(b1)
            
        visited = set()
        for start_node in list(adj.keys()):
            if start_node not in visited:
                cluster = []
                queue = deque([start_node])
                while queue:
                    curr = queue.popleft()
                    if curr not in visited:
                        visited.add(curr)
                        cluster.append(curr)
                        queue.extend(adj[curr] - visited)
                        
                if len(cluster) > 1:
                    self.groups.append(sorted(cluster))
        
        self.groups.sort(key=len, reverse=True)

    def setup_plot(self):
        self.fig = plt.figure(figsize=(18, 11))
        self.gs = self.fig.add_gridspec(3, 2, width_ratios=[1, 1.2], hspace=0.25, wspace=0.15, bottom=0.1)

        self.ax_air = self.fig.add_subplot(self.gs[0, 1])
        self.ax_skin = self.fig.add_subplot(self.gs[1, 1], sharex=self.ax_air)
        self.ax_press = self.fig.add_subplot(self.gs[2, 1], sharex=self.ax_air)

        # UI Elements
        ax_prev = plt.axes([0.1, 0.02, 0.08, 0.04])
        ax_next = plt.axes([0.19, 0.02, 0.08, 0.04])
        self.b_prev = Button(ax_prev, '<< Prev Group')
        self.b_next = Button(ax_next, 'Next Group >>')
        self.b_prev.on_clicked(self.prev_group)
        self.b_next.on_clicked(self.next_group)

        ax_slider = plt.axes([0.35, 0.03, 0.55, 0.025])
        self.slider = Slider(ax_slider, "Group", 0, len(self.groups)-1, valinit=0, valstep=1)
        self.slider.on_changed(self.on_slider_change)

        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)
    
    def remove_gps_outliers(self, df, max_deviation_km=25.0):
        """
        Removes severe GPS spikes by comparing each point to a rolling median.
        """
        if len(df) < 3:
            return df
            
        lat_med = df['Lat'].rolling(window=5, center=True, min_periods=1).median()
        lon_med = df['Lon'].rolling(window=5, center=True, min_periods=1).median()
        
        dist_km = self.haversine(df['Lat'], df['Lon'], lat_med, lon_med)
        
        return df[dist_km < max_deviation_km]

    def update_plot(self):
        group_ids = self.groups[self.current_idx]
        
        # --- MAP RE-DRAW ---
        if self.ax_map: 
            self.ax_map.remove()
        
        ref_lat = self.buoy_data[group_ids[0]]['Lat'].mean()
        proj = ccrs.NorthPolarStereo() if ref_lat > 0 else ccrs.SouthPolarStereo()
        extent = [-180, 180, 60, 90] if ref_lat > 0 else [-180, 180, -90, -60]

        self.ax_map = self.fig.add_subplot(self.gs[:, 0], projection=proj)
        self.ax_map.set_extent(extent, ccrs.PlateCarree())
        self.ax_map.add_feature(cfeature.LAND, facecolor='#e0e0e0')
        self.ax_map.add_feature(cfeature.COASTLINE, linewidth=0.5)
        
        # --- TIME SERIES CLEAR ---
        self.ax_air.clear()
        self.ax_skin.clear()
        self.ax_press.clear()

        # --- PLOT MEMBERS ---
        for i, bid in enumerate(group_ids):
            df = self.buoy_data[bid]
            color = self.colors[i % len(self.colors)]
            label = f"{bid} ({df['Type'].iloc[0]})"

            df_clean = self.remove_gps_outliers(df)
            
            # Map
            self.ax_map.plot(df_clean['Lon'], df_clean['Lat'], transform=ccrs.Geodetic(), 
                             color=color, linewidth=1.5, label=bid, alpha=0.8)
            self.ax_map.scatter(df_clean['Lon'].iloc[-1], df_clean['Lat'].iloc[-1], 
                                color=color, s=30, transform=ccrs.Geodetic(), zorder=10)

            # Air Temperature
            self.ax_air.plot(df.index, df['T2m_C'], color=color, alpha=0.8, label=label)
            
            # Skin Temperature
            if df['Ts_C'].notna().any():
                self.ax_skin.plot(df.index, df['Ts_C'], color=color, alpha=0.8)
                
            # Pressure
            if df['Press_hPa'].notna().any():
                self.ax_press.plot(df.index, df['Press_hPa'], color=color, alpha=0.8)

        # Formatting
        self.ax_map.set_title(f"Group {self.current_idx+1}: {len(group_ids)} Buoys")
        self.ax_air.set_ylabel("Air Temp (°C)")
        self.ax_skin.set_ylabel("Skin Temp (°C)")
        self.ax_press.set_ylabel("Pressure (hPa)")
        
        self.ax_air.legend(loc='upper left', fontsize=8, ncol=2)
        for ax in [self.ax_air, self.ax_skin, self.ax_press]:
            ax.grid(True, linestyle=':', alpha=0.6)

        date_fmt = mdates.DateFormatter('%m-%d')
        self.ax_press.xaxis.set_major_formatter(date_fmt)
        plt.setp(self.ax_press.xaxis.get_majorticklabels(), rotation=30, ha='right')

        # Silently update slider to reflect the current group 
        # (eventson=False prevents the on_changed callback from firing recursively)
        self.slider.eventson = False
        self.slider.set_val(self.current_idx)
        self.slider.eventson = True

        self.fig.canvas.draw_idle()

    def next_group(self, event=None):
        self.set_index((self.current_idx + 1) % len(self.groups))

    def prev_group(self, event=None):
        self.set_index((self.current_idx - 1) % len(self.groups))

    def on_slider_change(self, val):
        self.set_index(int(val))

    def on_key_press(self, event):
        if event.key == 'right': self.next_group()
        elif event.key == 'left': self.prev_group()

    def set_index(self, idx):
        if idx != self.current_idx:
            self.current_idx = idx
            self.update_plot()

if __name__ == "__main__":
    GroupValidationViewer(DATA_DIR)