{
  description = "Diego0160's GitHub profile README, built with Nix";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        # The build only *prepares* the generator script. Execution happens
        # via `nix run`, outside the Nix sandbox, so GITHUB_TOKEN from the
        # runner environment is available to the script at runtime.
        packages.profile-readme = pkgs.writeShellApplication {
          name = "profile-readme";
          runtimeInputs = [ pkgs.python3 ];
          text = ''
            python3 ${./generator/generate.py} \
              --username Diego0160 \
              --template ${./generator/template.md} \
              --output README.md
          '';
        };

        packages.default = self.packages.${system}.profile-readme;

        devShells.default = pkgs.mkShell {
          buildInputs = [ pkgs.python3 ];
        };
      }
    );
}