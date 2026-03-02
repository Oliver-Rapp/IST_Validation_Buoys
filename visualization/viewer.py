import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button, Slider
from pathlib import Path
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import warnings

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "validation_output" / "ist_txt"

class ValidationViewer:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.buoy_data = {} 
        self.buoy_ids = []
        self.current_idx = 0
        
        self.ax_map = None
        self.ax_top = None
        self.ax_top_r = None
        self.ax_bot = None
        self.ax_bot_r = None
        
        # -9: No QC / no data, 0: Valid+representative, 1: Valid+non-representative, 2: Invalid
        self.flag_colors = {-9: 'gray', 0: 'tab:blue', 1: 'tab:orange', 2: 'tab:red'}
        
        print("Loading dataset...")
        self.load_data()
        
        if not self.buoy_ids:
            print("No data found!")
            return

        print(f"Loaded {len(self.buoy_ids)} buoys.")
        
        self.setup_plot()
        self.update_plot()
        plt.show()

    def load_data(self):
        files = list(self.data_dir.rglob("*.txt"))
        if not files: return

        col_names = [
            'ID', 'Type', 'Lat', 'Lon', 'Year', 'Month', 'Day', 'Hour', 'Minute', 
            'Ts', 'T2m', 'Td', 'Press', 'FF', 'DD', 'Cloud', 'Ts_Qual', 'T2m_Qual'
        ]

        df_list = []
        for f in files:
            try:
                df = pd.read_csv(f, delim_whitespace=True, names=col_names, header=None)
                df_list.append(df)
            except Exception: pass

        if not df_list: return

        full_df = pd.concat(df_list, ignore_index=True)
        full_df['Datetime'] = pd.to_datetime(full_df[['Year', 'Month', 'Day', 'Hour', 'Minute']])
        
        # Clean Data
        full_df['Ts_C'] = np.where(full_df['Ts'] > 0, full_df['Ts'] - 273.15, np.nan)
        full_df['T2m_C'] = np.where(full_df['T2m'] > 0, full_df['T2m'] - 273.15, np.nan)
        full_df['Press_hPa'] = np.where(full_df['Press'] > 800, full_df['Press'], np.nan)
        full_df['FF_ms'] = np.where(full_df['FF'] >= 0, full_df['FF'], np.nan)
        full_df['DD_deg'] = np.where(full_df['DD'] >= 0, full_df['DD'], np.nan)
        full_df['T_Diff'] = full_df['Ts_C'] - full_df['T2m_C']

        for bid, group in full_df.groupby('ID'):
            group = group.sort_values('Datetime').set_index('Datetime')
            
            # Calculate 24h Peak-to-Peak variance for SVP/CALIB visualization
            rolling_24h = group['T2m_C'].rolling('24h', center=True)
            group['T2m_PTP'] = rolling_24h.max() - rolling_24h.min()
            
            self.buoy_data[bid] = group
            self.buoy_ids.append(bid)
            
        self.buoy_ids.sort()

    def setup_plot(self):
        self.fig = plt.figure(figsize=(16, 10))
        self.gs = self.fig.add_gridspec(2, 2, width_ratios=[1, 1.5], height_ratios=[1, 1], bottom=0.1)

        self.ax_top = self.fig.add_subplot(self.gs[0, 1])
        self.ax_bot = self.fig.add_subplot(self.gs[1, 1], sharex=self.ax_top)

        ax_prev = plt.axes([0.05, 0.025, 0.08, 0.04])
        ax_next = plt.axes([0.14, 0.025, 0.08, 0.04])
        self.b_prev = Button(ax_prev, '<< Prev')
        self.b_next = Button(ax_next, 'Next >>')
        self.b_prev.on_clicked(self.prev_buoy)
        self.b_next.on_clicked(self.next_buoy)

        ax_slider = plt.axes([0.30, 0.035, 0.60, 0.02])
        self.slider = Slider(
            ax_slider, "Buoy Index", 0, len(self.buoy_ids)-1, 
            valinit=0, valstep=1, color='gray'
        )
        self.slider.on_changed(self.on_slider_change)

        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)

    def update_plot(self):
        bid = self.buoy_ids[self.current_idx]
        df = self.buoy_data[bid]
        
        self.fig.canvas.manager.set_window_title(f"QC Inspector - {bid}")

        if self.ax_map is not None:
            self.ax_map.remove()

        mean_lat = df['Lat'].mean()
        if mean_lat < 0:
            proj = ccrs.SouthPolarStereo()
            extent = [-180, 180, -90, -50]
        else:
            proj = ccrs.NorthPolarStereo()
            extent = [-180, 180, 60, 90]

        self.ax_map = self.fig.add_subplot(self.gs[:, 0], projection=proj)
        try: self.ax_map.set_extent(extent, ccrs.PlateCarree())
        except: pass

        self.ax_map.add_feature(cfeature.LAND, facecolor='#d3d3d3')
        self.ax_map.add_feature(cfeature.COASTLINE, linewidth=0.5)
        self.ax_map.gridlines(draw_labels=False, alpha=0.3)
        
        self.ax_map.scatter(df['Lon'], df['Lat'], c=df.index.view(np.int64), 
                            cmap='viridis', s=10, transform=ccrs.PlateCarree(), zorder=5)
        self.ax_map.text(df['Lon'].iloc[0], df['Lat'].iloc[0], 'S', transform=ccrs.PlateCarree(), color='green', fontweight='bold', zorder=10)
        self.ax_map.text(df['Lon'].iloc[-1], df['Lat'].iloc[-1], 'E', transform=ccrs.PlateCarree(), color='red', fontweight='bold', zorder=10)
        self.ax_map.set_title(f"{bid} ({df['Type'].iloc[0]})")

        if self.ax_top_r: self.ax_top_r.remove(); self.ax_top_r = None
        if self.ax_bot_r: self.ax_bot_r.remove(); self.ax_bot_r = None
        
        self.ax_top.clear()
        self.ax_bot.clear()

        # Check if this buoy has a valid skin temperature profile
        has_skin = df['Ts_C'].notna().any()
        
        # --- TOP PLOT ---
        if has_skin:
            # Thermistor Buoys: Plot Air temp as line, Skin temp as colored scatter
            self.ax_top.plot(df.index, df['T2m_C'], color='tab:green', linewidth=1.5, alpha=0.7, label='Air Temp')
            for flag, color in self.flag_colors.items():
                subset = df[df['Ts_Qual'] == flag]
                if not subset.empty:
                    self.ax_top.scatter(subset.index, subset['Ts_C'], color=color, s=12, zorder=5, label=f"Skin Q{flag}")
            self.ax_top.set_ylabel("Temp (°C)")
        else:
            # SVP/CALIB Buoys: Plot Air Temp colored by its own QC Flag
            self.ax_top.plot(df.index, df['T2m_C'], color='gray', linewidth=1.0, alpha=0.4) # Faint connecting line
            for flag, color in self.flag_colors.items():
                subset = df[df['T2m_Qual'] == flag]
                if not subset.empty:
                    self.ax_top.scatter(subset.index, subset['T2m_C'], color=color, s=12, zorder=5, label=f"Temp Q{flag}")
            
            self.ax_top.set_ylabel("Temp (°C)")
            self.ax_top_r = self.ax_top.twinx()
            self.ax_top_r.plot(df.index, df['Press_hPa'], color='black', linewidth=1, linestyle='--', alpha=0.6, label='Pressure')
            self.ax_top_r.set_ylabel("hPa")

        # Combine legends dynamically
        handles, labels = self.ax_top.get_legend_handles_labels()
        if self.ax_top_r:
            h2, l2 = self.ax_top_r.get_legend_handles_labels()
            handles.extend(h2)
            labels.extend(l2)
        self.ax_top.legend(handles, labels, loc='upper left', fontsize=8)
        self.ax_top.grid(True, linestyle=':', alpha=0.6)

        # --- BOTTOM PLOT ---
        if has_skin:
            # Difference Plot for Thermistor buoys
            self.ax_bot.plot(df.index, df['T_Diff'], color='purple', linewidth=1)
            self.ax_bot.axhline(0, color='black', linewidth=1)
            self.ax_bot.fill_between(df.index, df['T_Diff'], 0, where=(df['T_Diff']<0), color='blue', alpha=0.1)
            self.ax_bot.fill_between(df.index, df['T_Diff'], 0, where=(df['T_Diff']>0), color='red', alpha=0.1)
            self.ax_bot.set_ylabel("Ts - T2m (°C)")
        else:
            # 24h peak-to-peak temperature variance for SVP/CALIB
            self.ax_bot.plot(df.index, df['T2m_PTP'], color='purple', linewidth=1.5, label='24h Peak-to-Peak Variance')
            
            self.ax_bot.set_ylabel("24h Temp Range (°C)")
            
            # Dynamic Y-limit so a single 15C spike doesn't squash the whole variance plot
            y_max = df['T2m_PTP'].max()
            if not pd.isna(y_max):
                self.ax_bot.set_ylim(0, min(10.0, y_max * 1.1)) 
            
            self.ax_bot.legend(loc='upper left', fontsize=8)

        self.ax_bot.grid(True, linestyle=':', alpha=0.6)
        
        # Formatting
        date_fmt = mdates.DateFormatter('%m-%d')
        self.ax_bot.xaxis.set_major_formatter(date_fmt)
        plt.setp(self.ax_bot.xaxis.get_majorticklabels(), rotation=30, ha='right')

        # Update slider label silently
        self.slider.valtext.set_text(f"{self.current_idx}: {bid}")
        
        self.fig.canvas.draw_idle()

    def next_buoy(self, event=None):
        self.set_index((self.current_idx + 1) % len(self.buoy_ids))

    def prev_buoy(self, event=None):
        self.set_index((self.current_idx - 1) % len(self.buoy_ids))
        
    def on_key_press(self, event):
        if event.key == 'right': self.next_buoy()
        elif event.key == 'left': self.prev_buoy()
        
    def on_slider_change(self, val):
        self.set_index(int(val))

    def set_index(self, idx):
        if idx != self.current_idx:
            self.current_idx = idx
            self.slider.eventson = False
            self.slider.set_val(idx)
            self.slider.eventson = True
            self.update_plot()

if __name__ == "__main__":
    ValidationViewer(DATA_DIR)