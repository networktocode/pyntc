# `arista_eos_ssh` mock fixtures

Golden CLI output for `EOSSSHDevice` unit tests. Loaded by `get_side_effects()` in `tests/unit/conftest.py` — any string in a side-effect list naming a file here is replaced by that file's contents.

## Provenance

Captured from a real **Arista DCS-7050TX-64-R running EOS 4.28.5M**, over SSH, via `show <command> | json`. This capture is what confirmed the driver's central design assumption: the `| json` pipe returns the same document, with the same key names, that eAPI returns — without eAPI being involved.

| Fixture | Source |
| --- | --- |
| `show_version_json` | real capture, `show version \| json` |
| `show_hostname_json` | real capture, `show hostname \| json` |
| `show_interfaces_status_json` | real capture, `show interfaces status \| json` (65 interfaces) |
| `show_boot-config_json` | real capture, `show boot-config \| json` |
| `show_vlan_json` | real capture, `show vlan \| json` |
| `dir` | real capture, `dir` |
| `show_boot` | real capture, `show boot` |
| `show_running-config` | **not** from hardware — the repo's sanitised vEOS config (see below) |
| `show_startup-config` | **not** from hardware — the repo's sanitised vEOS config (see below) |

### Sanitisation

Three values were replaced in `show_version_json`; everything else is verbatim:

- `serialNumber` → `JPE00000000`
- `systemMacAddress` / `hwMacAddress` → `00:1c:73:00:00:01`

And in `show_interfaces_status_json`, the `Ethernet1` description was replaced with `lab uplink` (it named a client).

### Why the configs are not real captures

`running_config` and `startup_config` are returned verbatim by the driver and never parsed, so a real capture would validate nothing — while writing device hostnames, SNMP communities and password hashes into a committed test tree. Those two files are the repo's existing sanitised vEOS config, kept only so the tests have non-empty text to work with. That is why they say `eos-spine1` while every other fixture says `nyc-eos-01`.

The one genuine risk those commands carry is that a config line beginning with `% ` (inside a banner, say) would false-positive the driver's CLI error regex and make `running_config` raise on a healthy device. That was checked directly on hardware with `show running-config | include ^%` — no matches. `design-notes/capture_eos_ssh_fixtures.py` re-runs that scan and reports only a line count, never content.

## Edge cases this capture pins down

Both were absent from the older vEOS fixtures and would have gone untested:

- **`softwareImage` carries a `flash:/` prefix** (`flash:/EOS-4.28.5M.swi`). `boot_options` strips it with `.replace("flash:/", "")`; the vEOS fixture had no prefix, so that line had never been exercised against realistic input.
- **`Management1` is routed and has no `vlanId`** inside `vlanInformation`. The interface key map must resolve that to `None` rather than raising.
