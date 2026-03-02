import pandas as pd
import numpy as np

class SimbaInterfaceDetector:
    """
    Algorithms for detecting interfaces (air/snow, snow/ice) from SIMBA 
    thermistor string profiles.
    
    Note regarding physical gradients:
    These algorithms currently compute gradients assuming a uniform sensor 
    spacing (dz = constant). While some legacy buoys employ variable spacing 
    (e.g., 2cm at the top, 10cm at the bottom), the upper section of the 
    string relevant to the snow/ice interface is almost universally uniform.
    """
    
    def __init__(self, df_temp):
        self.df_temp = df_temp
        self.t_vals = df_temp.values
        self.dates = df_temp.index
        self.n_steps, self.n_sensors = self.t_vals.shape

    def detect_liao_2018(self, threshold=0.4375):
        """ Original Max Peak detection """
        profiles = self.t_vals 
        grads = np.abs(np.diff(profiles, axis=1))
        grads[:, :5] = 0 
        
        max_indices = np.argmax(grads, axis=1) 
        max_vals = np.max(grads, axis=1)       
        
        detected_idx = np.where(max_vals >= threshold, max_indices + 1, np.nan)
        s_result = pd.Series(detected_idx, index=self.df_temp.index)
        
        # Forward fill to handle periods of isothermal summer noise
        return s_result.ffill()

    def detect_leading_edge(self, threshold=0.4375, edge_ratio=0.2):
        """
        1. Finds the Max Gradient Peak (Liao).
        2. Backtracks upwards to find where the gradient rises significantly (Leading Edge).
        
        edge_ratio: The fraction of the peak height defining the "edge".
        """
        profiles = self.t_vals 
        grads = np.abs(np.diff(profiles, axis=1))
        grads[:, :5] = 0
        grads[:, 150:] = 0
        
        peak_indices = np.argmax(grads, axis=1)
        peak_vals = np.max(grads, axis=1)
        
        results = np.full(self.n_steps, np.nan)
        
        for t in range(self.n_steps):
            p_idx = peak_indices[t]
            p_val = peak_vals[t]
            
            if p_val < threshold:
                if t > 0: results[t] = results[t-1]
                continue
                
            edge_threshold = p_val * edge_ratio
            segment = grads[t, :p_idx]
            
            low_grad_indices = np.where(segment < edge_threshold)[0]
            
            if len(low_grad_indices) > 0:
                results[t] = low_grad_indices[-1] + 1
            else:
                results[t] = p_idx + 1
                
        s_result = pd.Series(results, index=self.df_temp.index)
        return s_result.ffill()

