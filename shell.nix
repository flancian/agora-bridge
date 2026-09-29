{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = with pkgs; [
    gcc
    pkg-config
    libffi
    cargo
    rustc
    nodejs_22
    yarn
  ];
}
