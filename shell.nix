{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  name = "buoy-validation-env";

  buildInputs = [
    pkgs.python3

    # Core
    pkgs.python3Packages.numpy
    pkgs.python3Packages.pandas
    pkgs.python3Packages.scipy
    pkgs.python3Packages.matplotlib
    pkgs.python3Packages.pyyaml
    pkgs.python3Packages.requests
    pkgs.python3Packages.tqdm

    # Geospatial (C library dependencies handled by Nix)
    pkgs.python3Packages.cartopy
    pkgs.python3Packages.shapely
    pkgs.geos
    pkgs.proj

    # NetCDF / SvalMIZ input
    pkgs.python3Packages.xarray
    pkgs.python3Packages.netcdf4

    # Tkinter backend for interactive matplotlib windows
    pkgs.python3Packages.tkinter
  ];

  shellHook = ''
    export MPLBACKEND='TkAgg'
    echo "OSI SAF IST Validation environment ready."
  '';
}
