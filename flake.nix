{
  description = "Agora Bridge: connecting the distributed knowledge commons to the web and fediverse";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    let
      inherit (nixpkgs) lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = lib.genAttrs systems;

      workspace = uv2nix.lib.workspace.loadWorkspace {
        workspaceRoot = ./.;
      };

      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      pyprojectOverrides = final: prev: {
        sgmllib3k = prev.sgmllib3k.overrideAttrs (old: {
          nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ final.resolveBuildSystem { setuptools = [ ]; };
        });
      };
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};

          pythonSet = (pkgs.callPackage pyproject-nix.build.packages {
            python = pkgs.python312;
          }).overrideScope (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              overlay
              pyprojectOverrides
            ]
          );

          venv = pythonSet.mkVirtualEnv "agora-bridge-env" workspace.deps.default;

          agora-bridge = pkgs.stdenv.mkDerivation {
            pname = "agora-bridge";
            version = "0.1.0";
            src = lib.fileset.toSource {
              root = ./.;
              fileset = lib.fileset.unions [
                ./api
                ./bots
                ./bullpen
                ./scripts
                ./feed.py
                ./import_mediawiki.py
                ./import_stoa.py
                ./import_wayback.py
                ./import_website.py
                ./pull.py
              ];
            };

            installPhase = ''
              runHook preInstall

              mkdir -p $out/share/agora-bridge $out/bin
              cp -r api bots bullpen scripts feed.py import_*.py pull.py $out/share/agora-bridge/

              cat > $out/share/agora-bridge/nix-env.sh <<EOF
              export PATH="${lib.makeBinPath [ pkgs.git venv ]}:\$PATH"
              export PYTHONPATH="$out/share/agora-bridge\''${PYTHONPATH:+:\$PYTHONPATH}"
              if [ -z "\''${SSL_CERT_FILE:-}" ] || [ ! -r "\''${SSL_CERT_FILE}" ]; then
                export SSL_CERT_FILE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
              fi
              export LD_LIBRARY_PATH="${lib.makeLibraryPath [ pkgs.file ]}\''${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
              EOF

              cat > $out/bin/agora-bridge <<EOF
              #!${pkgs.runtimeShell}
              set -euo pipefail
              source "$out/share/agora-bridge/nix-env.sh"
              export FLASK_APP=api
              export FLASK_ENV="\''${FLASK_ENV:-production}"
              exec ${venv}/bin/gunicorn \
                --chdir "$out/share/agora-bridge" \
                -w "\''${GUNICORN_WORKERS:-4}" \
                -b "0.0.0.0:\''${PORT:-5018}" \
                "api:create_app()" "\$@"
              EOF
              chmod +x $out/bin/agora-bridge

              for pair in \
                "agora-pull:pull.py" \
                "agora-import-stoa:import_stoa.py" \
                "agora-feed:feed.py"
              do
                bin_name="''${pair%%:*}"
                script_name="''${pair#*:}"
                cat > "$out/bin/$bin_name" <<EOF
              #!${pkgs.runtimeShell}
              set -euo pipefail
              source "$out/share/agora-bridge/nix-env.sh"
              exec ${venv}/bin/python3 "$out/share/agora-bridge/$script_name" "\$@"
              EOF
                chmod +x "$out/bin/$bin_name"
              done

              runHook postInstall
            '';

            meta = {
              description = "Agora Bridge: connecting the distributed knowledge commons";
              homepage = "https://anagora.org";
              mainProgram = "agora-bridge";
            };
          };
        in
        {
          default = agora-bridge;
          inherit agora-bridge venv;
        }
      );

      apps = forAllSystems (
        system:
        let
          pkg = self.packages.${system}.agora-bridge;
        in
        {
          default = {
            type = "app";
            program = "${pkg}/bin/agora-bridge";
          };
          agora-bridge = {
            type = "app";
            program = "${pkg}/bin/agora-bridge";
          };
          pull = {
            type = "app";
            program = "${pkg}/bin/agora-pull";
          };
          import-stoa = {
            type = "app";
            program = "${pkg}/bin/agora-import-stoa";
          };
          feed = {
            type = "app";
            program = "${pkg}/bin/agora-feed";
          };
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python312
              uv
              git
              gcc
              pkg-config
              libffi
              file
            ];
          };
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          agora-bridge = self.packages.${system}.agora-bridge;
        in
        {
          smoke-test = pkgs.runCommand "agora-bridge-smoke-test" {
            nativeBuildInputs = [ pkgs.curl ];
          } ''
            set -euo pipefail
            export HOME="$TMPDIR/home"
            mkdir -p "$HOME/agora/garden/agora"
            cat > "$HOME/agora/sources.yaml" <<YAML
            - target: garden/agora
              url: https://example.com/agora.git
              format: markdown
            YAML

            ${agora-bridge}/bin/agora-pull --help > /dev/null

            export PORT=15018
            export GUNICORN_WORKERS=1

            ${agora-bridge}/bin/agora-bridge > "$TMPDIR/bridge.log" 2>&1 &
            PID=$!
            trap 'kill "$PID" 2>/dev/null || true' EXIT

            for i in $(seq 1 30); do
              if curl -fsS "http://127.0.0.1:$PORT/" > "$TMPDIR/index.html"; then
                break
              fi
              sleep 0.5
            done

            if ! grep -qi "Agora" "$TMPDIR/index.html"; then
              cat "$TMPDIR/bridge.log"
              exit 1
            fi

            touch "$out"
          '';
        }
      );
    };
}
