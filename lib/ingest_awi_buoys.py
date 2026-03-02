import os
import shutil
import requests
import zipfile
from pathlib import Path
from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)

# AWI Data URLs — fallback defaults used when not provided via buoy_config.yaml
_DEFAULT_URLS = {
    "Arctic": "https://data.meereisportal.de/data/buoys/processed/Arctic/arctic_buoy_data.zip",
    "Antarctic": "https://data.meereisportal.de/data/buoys/processed/Antarctic/antarctic_buoy_data.zip"
}

def download_url(url, save_path):
    """Stream downloads a file with a progress bar."""
    logger.info(f"Downloading {url}...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        
        with open(save_path, 'wb') as file, tqdm(
            desc=save_path.name,
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for data in response.iter_content(chunk_size=8192):
                size = file.write(data)
                bar.update(size)
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        return False
    return True

def process_zip(zip_path, temp_dir, destination_dir, min_year=None):
    """Unzips, filters by year, and moves to destination."""
    logger.info(f"Extracting {zip_path.name}...")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(temp_dir)
    except zipfile.BadZipFile:
        logger.error(f"Error: {zip_path} is corrupted.")
        return

    files = list(temp_dir.rglob("*.csv"))
    moved_count = 0
    skipped_count = 0
    
    filter_msg = f" (Min Year: {min_year})" if min_year else " (No year filter)"
    logger.info(f"Filtering and moving files{filter_msg}...")
    
    for file_path in files:
        filename = file_path.name
        
        try:
            # Default to moving it unless we can prove it's too old
            should_move = True
            
            if min_year is not None:
                year_str = filename[:4]
                if year_str.isdigit() and int(year_str) < min_year:
                    should_move = False

            if should_move:
                # Move and overwrite if exists
                shutil.move(str(file_path), str(destination_dir / filename))
                moved_count += 1
            else:
                skipped_count += 1
                
        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")

    logger.info(f"  -> Kept: {moved_count} | Discarded (Too old): {skipped_count}")

def run_ingest(destination_dir, min_year=None, clear_existing=True, urls=None):
    """
    Main entry point for downloading and extracting buoy data.

    Args:
        destination_dir: Directory to store extracted buoy files.
        min_year: Discard files older than this year (saves disk space).
        clear_existing: If True, performs a 'Smart Wipe' — deletes CSVs and
                        temp folders but PROTECTS manually-added NetCDF files.
        urls: Dict mapping region name → zip URL. Reads from buoy_config.yaml
              defaults.awi_urls; falls back to built-in URLs if not provided.
    """
    urls = urls or _DEFAULT_URLS
    dest = Path(destination_dir)
    dest.mkdir(parents=True, exist_ok=True)
    
    # --- SMART CLEANUP ---
    if clear_existing and dest.exists():
        logger.info(f"Cleaning raw data directory (Preserving .nc files)...")
        
        # Iterate over items in the directory
        for item in dest.iterdir():
            # 1. Protect NetCDF files
            if item.is_file() and item.suffix.lower() == '.nc':
                logger.info(f"  [Protected] {item.name}")
                continue
            
            # 2. Delete everything else (CSVs, old zips, folders)
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception as e:
                logger.warning(f"Could not delete {item}: {e}")

    # --- DOWNLOAD & EXTRACT ---
    temp_dir = dest / "temp_extract"
    temp_dir.mkdir(exist_ok=True)

    for region, url in urls.items():
        zip_path = temp_dir / f"{region}_buoys.zip"
        success = download_url(url, zip_path)
        if success:
            process_zip(zip_path, temp_dir, dest, min_year)
            zip_path.unlink() # Cleanup Zip immediately to save space

    logger.info("Cleaning up temporary extraction files...")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        
    logger.info(f"Done. Data stored in {dest}")