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
        packages.profile-readme = pkgs.stdenv.mkDerivation {
          name = "profile-readme";
          src = self;
          buildInputs = [ pkgs.python3 ];
          buildPhase = ''
            GITHUB_TOKEN="''${GITHUB_TOKEN:-}" \
            python generator/generate.py \
              --username Diego0160 \
              --template generator/template.md \
              --output $out/README.md
          '';
          installPhase = ''
            true
          '';
        };

        packages.default = self.packages.${system}.profile-readme;

        devShells.default = pkgs.mkShell {
          buildInputs = [ pkgs.python3 ];
        };
      }
    );
}
