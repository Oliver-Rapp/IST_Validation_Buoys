import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider
import warnings
import os
import copy
import sys
from pathlib import Path

# --- PROJECT ROOT (works wherever this script is placed in the repo tree) ---
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# --- IMPORTS ---
from lib.config_manager import BuoyConfig
from lib import data_loader
from lib import simba_algo
from lib import simba_qc

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
TARGET_BUOY = "2022T92"  # Example default: SIMB3 Buoys usually have the sonar
CONFIG_FILE = str(_PROJECT_ROOT / "buoy_config.yaml")
INPUT_DIR = os.environ.get("BUOY_DATA_DIR", str(_PROJECT_ROOT / "data" / "raw"))
START_DATE = "2024-09-08" 

class ModularInspector:
    def __init__(self, df_string, df_meta, s_interface, s_tair, df_qc, config):
        self.df_temp = df_string
        self.df_meta = df_meta
        self.s_interface = s_interface
        self.s_tair = s_tair
        self.df_qc = df_qc
        self.config = config
        
        self.timestamps = df_string.index
        self.n_steps = len(self.timestamps)
        self.t_vals = df_string.values
        self.sensors = np.arange(self.t_vals.shape[1])
        
        try:
            self.curr_idx = self.timestamps.get_indexer([pd.Timestamp(START_DATE)], method='nearest')[0]
        except:
            self.curr_idx = 0

        self.fig = plt.figure(figsize=(18, 10))
        gs = self.fig.add_gridspec(2, 3, height_ratios=[2, 1], hspace=0.3, wspace=0.15)
        
        self.ax1 = self.fig.add_subplot(gs[0, 0]) 
        self.ax2 = self.fig.add_subplot(gs[0, 1], sharey=self.ax1) 
        self.ax3 = self.fig.add_subplot(gs[0, 2], sharey=self.ax1) 
        self.ax4 = self.fig.add_subplot(gs[1, :]) 
        
        ax_slider = plt.axes([0.15, 0.02, 0.7, 0.02])
        self.slider = Slider(ax_slider, 'Time Step', 0, self.n_steps - 1, valinit=self.curr_idx, valstep=1)
        self.slider.on_changed(self.update)
        
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)
        self.draw_frame(self.curr_idx)
        plt.show()

    def draw_frame(self, idx):
        self.ax1.clear()
        self.ax2.clear()
        self.ax3.clear()
        self.ax4.clear()
        
        ts = self.timestamps[idx]
        profile = self.t_vals[idx, :]
        
        grad1 = np.abs(np.diff(profile))
        grad2 = np.diff(grad1)
        
        val_edge = self.s_interface.iloc[idx]
        val_tair = self.s_tair.get(ts, np.nan)
        qc_data = self.df_qc.iloc[idx]
        
        val_sonar_idx = np.nan
        if 'snow_dist' in self.df_meta.columns:
            dist_m = self.df_meta['snow_dist'].iloc[idx]
            geom = self.config.get('geometry', {})
            h_sonar = geom.get('sonar_height_m', 1.5)
            spacing = geom.get('sensor_spacing_m', 0.02)
            
            if not pd.isna(dist_m) and dist_m > 0:
                val_sonar_idx = (h_sonar - dist_m) / spacing

        thresh = self.config['algorithm']['params']['threshold']

        # --- AX1: Temp Profile ---
        self.ax1.plot(profile, self.sensors, 'b-o', markersize=3, alpha=0.4)
        
        if not np.isnan(val_tair):
            self.ax1.axvline(val_tair, color='orange', linestyle='--', linewidth=1.5, label='Air Temp')
        
        if not np.isnan(val_edge):
            self.ax1.axhline(val_edge, color='magenta', linewidth=2, label='Leading Edge')
            try: self.ax1.plot(profile[int(val_edge)-1], val_edge, 'mo', markersize=8)
            except: pass

        if not np.isnan(val_sonar_idx):
            self.ax1.axhline(val_sonar_idx, color='gold', linestyle='--', linewidth=2.5, label='Sonar Surface')

        self.ax1.set_ylim(len(self.sensors), 0)
        self.ax1.set_title(f"Buoy: {TARGET_BUOY} | {ts}")
        self.ax1.grid(True)
        self.ax1.legend(loc='lower left', fontsize=8)

        # --- AX2: Gradient ---
        self.ax2.plot(grad1, self.sensors[:-1], 'k-')
        if not np.isnan(val_edge): self.ax2.axhline(val_edge, color='magenta', linewidth=2)
        if not np.isnan(val_sonar_idx): self.ax2.axhline(val_sonar_idx, color='gold', linestyle='--', linewidth=1.5)
        
        self.ax2.axvline(thresh, color='gray', linestyle=':', label='Threshold')
        self.ax2.set_xlabel("|dT/dz|")
        self.ax2.set_xlim(0, 1.5)
        self.ax2.grid(True)

        # --- AX3: Curvature ---
        self.ax3.plot(grad2, self.sensors[:-2], 'g-')
        self.ax3.axvline(0, color='k', linestyle=':', alpha=0.3)
        if not np.isnan(val_edge): self.ax3.axhline(val_edge, color='magenta', linewidth=2)
        self.ax3.set_xlabel("d2T/dz2")
        self.ax3.set_xlim(-0.5, 0.5)
        self.ax3.grid(True)

        # Info Box
        flag_map = {-9: 'NO QC', 0: 'GOOD', 1: 'NON-REP', 2: 'INVALID'}
        flag_str = flag_map.get(int(qc_data['quality_flag']), 'UNKNOWN')
        
        # Safely extract sonar distance for display
        if 'snow_dist' in self.df_meta.columns and not pd.isna(self.df_meta['snow_dist'].iloc[idx]):
            sonar_dist_str = f"{self.df_meta['snow_dist'].iloc[idx]:.3f}m"
        else:
            sonar_dist_str = "N/A"

        stats_text = (
            f"TYPE: {self.config['station_type'].strip()}\n"
            f"SONAR DIST: {sonar_dist_str}\n"
            f"LEAD EDGE: {val_edge:.0f}\n"
            f"SONAR IDX: {val_sonar_idx:.1f}\n"
            f"------------------\n"
            f"FLAG: {flag_str} ({int(qc_data['quality_flag'])})"
        )
        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        self.ax3.text(0.95, 0.95, stats_text, transform=self.ax3.transAxes, fontsize=10,
                    verticalalignment='top', horizontalalignment='right', bbox=props, family='monospace')

        # --- AX4: QC ---
        self.ax4.plot(self.df_qc.index, self.df_qc['total_conf'], 'g-', alpha=0.6)
        self.ax4.axvline(ts, color='r', linewidth=2)
        self.ax4.set_ylim(0, 105)
        self.ax4.grid(True)

    def update(self, val):
        self.curr_idx = int(val)
        self.draw_frame(self.curr_idx)
        self.fig.canvas.draw_idle()

    def on_key(self, event):
        if event.key == 'right':
            self.curr_idx = min(self.curr_idx + 1, self.n_steps - 1)
            self.slider.set_val(self.curr_idx)
        elif event.key == 'left':
            self.curr_idx = max(self.curr_idx - 1, 0)
            self.slider.set_val(self.curr_idx)

def main():
    print(f"Inspecting {TARGET_BUOY}...")
    
    cfg_mgr = BuoyConfig(CONFIG_FILE)
    try:
        base_conf = cfg_mgr.get_config_for_id(TARGET_BUOY)
    except ValueError as e:
        print(e)
        return

    if base_conf['algorithm']['method'] == 'none':
        print(f"Buoy {TARGET_BUOY} has no thermistor string.")
        return

    conf = copy.deepcopy(base_conf)
    conf['files']['primary'] = f"{TARGET_BUOY}_{base_conf['files']['primary']}"
    if 'aux' in conf['files']:
        conf['files']['aux'] = f"{TARGET_BUOY}_{base_conf['files']['aux']}"

    print(f">> Loading data from {INPUT_DIR}...")
    df_meta, df_string = data_loader.load_buoy_data(INPUT_DIR, conf)
    
    if df_string is None:
        print("Error: String data could not be loaded.")
        return

    print(">> Running Algorithms...")
    detector = simba_algo.SimbaInterfaceDetector(df_string)
    
    algo_params = conf['algorithm']['params']
    s_interface = detector.detect_leading_edge(
        threshold=algo_params['threshold'], 
        edge_ratio=algo_params['edge_ratio']
    )
    
    s_tair = df_meta.get('air_temp', pd.Series(np.nan, index=df_meta.index))

    print(">> Running QC...")
    qc = simba_qc.SimbaQC(df_string, s_interface, conf.get('qc', {}).get('params'))
    df_scores = qc.compute_flags()
    
    s_tair = s_tair.reindex(df_string.index, method='nearest')
    
    print(">> Launching Inspector...")
    inspector = ModularInspector(df_string, df_meta, s_interface, s_tair, df_scores, conf)

if __name__ == "__main__":
    main()