# BMC

Insyde BMC firmware work. Recommended only on machines with `repo` and at least one local platform tree (`~/EVB2700_A2`, `~/Vera`, `~/OKS`, `~/AMDShared`).

- **[build-image](./build-image/SKILL.md)**: sync and bitbake `obmc-phosphor-image` for one or more platforms, retrying failed recipes with `do_cleanall`.
- **[gerrit-ci-retrigger](./gerrit-ci-retrigger/SKILL.md)**: check CI status of open Gerrit patches, classify failures, retrigger Jenkins builds.
